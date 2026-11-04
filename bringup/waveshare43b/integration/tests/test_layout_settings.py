#!/usr/bin/env python3
"""Integration tests for src/ws43b_layout_settings.cpp.

The real C++ module is copied verbatim into a temporary directory, paired with
test-only stubs for config.h and Preferences.h, compiled with clang++ and run.
The module implementation is never re-implemented in Python.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

# .../BambuHelper/bringup/waveshare43b/integration/tests/test_layout_settings.py
# parents[4] == BambuHelper/, so parents[4] / "src" is the module source dir.
SRC_DIR = Path(__file__).resolve().parents[4] / "src"
CPP_SRC = SRC_DIR / "ws43b_layout_settings.cpp"
HEADER_SRC = SRC_DIR / "ws43b_layout_settings.h"

CONFIG_STUB = """#pragma once
#define NVS_NAMESPACE "bambu_ws43b"
"""

# Scriptable Preferences stub. The harness drives it through the PREF_* env
# knobs baked into the stub's own argv-independent globals set by the harness.
# The static definitions are `inline` (C++17) so the header can be included by
# more than one translation unit without duplicate-symbol link errors.
PREFERENCES_STUB = """#pragma once
#include <stdint.h>
#include <string>
#include <map>
#include <vector>

class Preferences {
public:
    bool begin(const char *ns, bool readOnly) {
        opened_ = true;
        read_only_ = readOnly;
        ++begin_calls;
        begin_read_only.push_back(readOnly);
        if (begin_fails) return false;
        return true;
    }
    void end() {
        if (opened_) {
            ++end_calls;
            opened_ = false;
        }
    }
    uint16_t getUShort(const char *key, uint16_t defaultValue) {
        ++get_calls;
        auto it = store.find(key);
        if (it == store.end()) return defaultValue;
        if (get_fails) return get_default_value;
        return it->second;
    }
    size_t putUShort(const char *key, uint16_t value) {
        ++put_calls;
        if (read_only_) return 0;
        if (put_bytes == 0) return 0;
        // A short write is a failed write: it must not persist the value.
        if (put_bytes == sizeof(value)) store[key] = value;
        return put_bytes;
    }

    // Test-controlled state (set by the harness before invoking the module).
    static bool begin_fails;
    static size_t put_bytes;
    static int begin_calls;
    static int end_calls;
    static int get_calls;
    static int put_calls;
    static std::map<std::string, uint16_t> store;
    static std::vector<bool> begin_read_only;
    // Simulated NVS read error: getUShort returns the supplied default even
    // though the record exists in the stub store.
    static bool get_fails;
    static uint16_t get_default_value;

private:
    bool opened_ = false;
    bool read_only_ = false;
};

inline bool Preferences::begin_fails = false;
inline size_t Preferences::put_bytes = 2;
inline int Preferences::begin_calls = 0;
inline int Preferences::end_calls = 0;
inline int Preferences::get_calls = 0;
inline int Preferences::put_calls = 0;
inline std::map<std::string, uint16_t> Preferences::store;
inline std::vector<bool> Preferences::begin_read_only;
inline bool Preferences::get_fails = false;
inline uint16_t Preferences::get_default_value = 0;
"""

# Harness: exercises the module through its public API and prints a
# machine-readable report. Scenario is selected by argv[1].
HARNESS = r"""
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include "ws43b_layout_settings.h"
#include "Preferences.h"

static void resetPrefs() {
    Preferences::begin_fails = false;
    Preferences::put_bytes = 2;
    Preferences::begin_calls = 0;
    Preferences::end_calls = 0;
    Preferences::get_calls = 0;
    Preferences::put_calls = 0;
    Preferences::store.clear();
    Preferences::begin_read_only.clear();
    Preferences::get_fails = false;
    Preferences::get_default_value = 0;
}

static void report(const char *scenario) {
    printf("scenario=%s\n", scenario);
    printf("minimal=%d\n", ws43bMinimalLayout() ? 1 : 0);
    printf("revision=%u\n", ws43bLayoutRevision());
    printf("begin_calls=%d\n", Preferences::begin_calls);
    printf("end_calls=%d\n", Preferences::end_calls);
    printf("get_calls=%d\n", Preferences::get_calls);
    printf("put_calls=%d\n", Preferences::put_calls);
    auto it = Preferences::store.find("w43_layout");
    printf("nvs_w43_layout=%d\n", it == Preferences::store.end() ? -1 : (int)it->second);
    printf("nvs_other_keys=%d\n", (int)Preferences::store.size() -
           (Preferences::store.count("w43_layout") ? 1 : 0));
    for (size_t i = 0; i < Preferences::begin_read_only.size(); ++i) {
        printf("begin_read_only_%zu=%s\n", i,
               Preferences::begin_read_only[i] ? "true" : "false");
    }
    printf("begin_read_only_flags=%s", "");
    for (size_t i = 0; i < Preferences::begin_read_only.size(); ++i) {
        if (i) printf(",");
        printf("%s", Preferences::begin_read_only[i] ? "true" : "false");
    }
    printf("\n");
}

int main(int argc, char **argv) {
    const std::string scenario = argc > 1 ? argv[1] : "";

    if (scenario == "missing_record") {
        // NVS empty: getUShort returns the supplied default 0x0100.
        loadWs43bLayout();
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "corrupt_record") {
        Preferences::store["w43_layout"] = 0x0201; // high bits unknown
        loadWs43bLayout();
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "read_begin_fails") {
        Preferences::begin_fails = true;
        loadWs43bLayout();
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "read_values") {
        Preferences::store["w43_layout"] = 0x0100; // Standard
        loadWs43bLayout();
        printf("standard_minimal=%d\n", ws43bMinimalLayout() ? 1 : 0);
        Preferences::store["w43_layout"] = 0x0101; // Minimalist
        loadWs43bLayout();
        printf("minimalist_minimal=%d\n", ws43bMinimalLayout() ? 1 : 0);
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "round_trip_minimalist") {
        resetPrefs();
        // RAM starts at the module default (Standard); the save writes 0x0101
        // and a fresh load must read it back as Minimalist.
        loadWs43bLayout();
        bool ok = saveWs43bLayout(true); // -> Minimalist
        printf("save_minimal_ok=%d\n", ok ? 1 : 0);
        printf("record_after_save=%d\n", (int)Preferences::store["w43_layout"]);
        loadWs43bLayout();
        printf("minimal_after_reload=%d\n", ws43bMinimalLayout() ? 1 : 0);
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "round_trip_standard") {
        resetPrefs();
        // Force a real change to Standard so 0x0100 is written, then reload.
        loadWs43bLayout();
        (void)saveWs43bLayout(true);   // -> Minimalist
        bool ok = saveWs43bLayout(false); // -> Standard
        printf("save_standard_ok=%d\n", ok ? 1 : 0);
        printf("record_after_save=%d\n", (int)Preferences::store["w43_layout"]);
        loadWs43bLayout();
        printf("minimal_after_reload=%d\n", ws43bMinimalLayout() ? 1 : 0);
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "get_failure_falls_back_to_standard") {
        // Start from a real 0x0101 record, then save Standard (0x0100,
        // revision 1). getUShort then simulates an NVS error and returns the
        // supplied default; the module must fall back to Standard, reset the
        // revision and perform no writes.
        resetPrefs();
        Preferences::store["w43_layout"] = 0x0101;
        loadWs43bLayout();
        (void)saveWs43bLayout(false); // Minimalist -> Standard: revision 1
        Preferences::get_fails = true;
        Preferences::get_default_value = 0x0100;
        int putsBeforeLoad = Preferences::put_calls;
        int beginsBeforeLoad = Preferences::begin_calls;
        int endsBeforeLoad = Preferences::end_calls;
        loadWs43bLayout();
        Preferences::get_fails = false;
        printf("minimal_after_get_failure=%d\n", ws43bMinimalLayout() ? 1 : 0);
        printf("revision_after_get_failure=%u\n", ws43bLayoutRevision());
        printf("record_after_get_failure=%d\n",
               (int)Preferences::store["w43_layout"]);
        printf("extra_puts_after_get_failure=%d\n",
               Preferences::put_calls - putsBeforeLoad);
        printf("extra_begins_after_get_failure=%d\n",
               Preferences::begin_calls - beginsBeforeLoad);
        printf("extra_ends_after_get_failure=%d\n",
               Preferences::end_calls - endsBeforeLoad);
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "load_resets_revision") {
        Preferences::store["w43_layout"] = 0x0101;
        loadWs43bLayout();
        bool ok = saveWs43bLayout(false);
        printf("save_ok=%d\n", ok ? 1 : 0);
        printf("revision_before_load=%u\n", ws43bLayoutRevision());
        loadWs43bLayout();
        printf("revision_after_load=%u\n", ws43bLayoutRevision());
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "save_same_value_no_nvs") {
        Preferences::store["w43_layout"] = 0x0100;
        loadWs43bLayout();
        int before = Preferences::begin_calls;
        int beforePut = Preferences::put_calls;
        uint32_t beforeRevision = ws43bLayoutRevision();
        bool ok = saveWs43bLayout(false); // same as loaded Standard
        printf("save_ok=%d\n", ok ? 1 : 0);
        printf("extra_begin_calls=%d\n", Preferences::begin_calls - before);
        printf("extra_put_calls=%d\n", Preferences::put_calls - beforePut);
        printf("revision_after_same_save=%u\n", ws43bLayoutRevision());
        printf("revision_delta=%d\n",
               (int)(ws43bLayoutRevision() - beforeRevision));
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "revision_increments_once") {
        loadWs43bLayout();
        uint32_t before = ws43bLayoutRevision();
        bool ok = saveWs43bLayout(true);
        printf("save_ok=%d\n", ok ? 1 : 0);
        printf("revision_delta=%d\n", (int)(ws43bLayoutRevision() - before));
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "begin_put_fail_preserves_state") {
        // Seed a known RAM state: Minimalist, revision 1.
        Preferences::store["w43_layout"] = 0x0101;
        loadWs43bLayout();
        bool first = saveWs43bLayout(false); // Standard, revision 1
        (void)first;

        // begin() failure on a change attempt.
        Preferences::begin_fails = true;
        bool failed_begin = saveWs43bLayout(true);
        printf("failed_begin_return=%d\n", failed_begin ? 1 : 0);
        printf("minimal_after_failed_begin=%d\n", ws43bMinimalLayout() ? 1 : 0);
        printf("revision_after_failed_begin=%u\n", ws43bLayoutRevision());
        Preferences::begin_fails = false;

        // putUShort returning 0 bytes.
        Preferences::put_bytes = 0;
        int endBeforePut0 = Preferences::end_calls;
        bool failed_put0 = saveWs43bLayout(true);
        printf("failed_put0_return=%d\n", failed_put0 ? 1 : 0);
        printf("minimal_after_failed_put0=%d\n", ws43bMinimalLayout() ? 1 : 0);
        printf("revision_after_failed_put0=%u\n", ws43bLayoutRevision());
        printf("end_after_put0=%d\n", Preferences::end_calls - endBeforePut0);
        printf("record_after_put0=%d\n", (int)Preferences::store["w43_layout"]);

        // putUShort returning 1 byte (short write).
        Preferences::put_bytes = 1;
        int endBeforePut1 = Preferences::end_calls;
        bool failed_put1 = saveWs43bLayout(true);
        printf("failed_put1_return=%d\n", failed_put1 ? 1 : 0);
        printf("minimal_after_failed_put1=%d\n", ws43bMinimalLayout() ? 1 : 0);
        printf("revision_after_failed_put1=%u\n", ws43bLayoutRevision());
        printf("end_after_put1=%d\n", Preferences::end_calls - endBeforePut1);
        printf("record_after_put1=%d\n", (int)Preferences::store["w43_layout"]);
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "read_only_then_read_write") {
        loadWs43bLayout(); // read-only begin
        bool ok = saveWs43bLayout(true); // read-write begin
        printf("save_ok=%d\n", ok ? 1 : 0);
        report(scenario.c_str());
        return 0;
    }

    if (scenario == "other_keys_untouched") {
        Preferences::store["other_key_a"] = 0x1234;
        Preferences::store["other_key_b"] = 0x5678;
        loadWs43bLayout();
        bool ok = saveWs43bLayout(true);
        printf("save_ok=%d\n", ok ? 1 : 0);
        printf("other_a=%d\n", (int)Preferences::store["other_key_a"]);
        printf("other_b=%d\n", (int)Preferences::store["other_key_b"]);
        report(scenario.c_str());
        return 0;
    }

    fprintf(stderr, "unknown scenario: %s\n", scenario.c_str());
    return 2;
}
"""


def parse_report(text):
    data = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data


class LayoutSettingsIntegrationTest(unittest.TestCase):
    """Compile the untouched module with stubs and run scripted scenarios."""

    @classmethod
    def setUpClass(cls):
        if not CPP_SRC.is_file() or not HEADER_SRC.is_file():
            raise RuntimeError(
                f"module sources not found under {SRC_DIR}: "
                f"{CPP_SRC} / {HEADER_SRC}"
            )
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)

        # Copy the real module verbatim; never rewrite it.
        shutil.copyfile(CPP_SRC, tmp / "ws43b_layout_settings.cpp")
        shutil.copyfile(HEADER_SRC, tmp / "ws43b_layout_settings.h")
        (tmp / "config.h").write_text(CONFIG_STUB)
        (tmp / "Preferences.h").write_text(PREFERENCES_STUB)
        (tmp / "harness.cpp").write_text(HARNESS)

        cls.binary = tmp / "layout_test"
        compile_cmd = [
            "clang++",
            "-std=c++17",
            "-DBOARD_IS_WS43B",
            "-I", str(tmp),
            "-o", str(cls.binary),
            str(tmp / "ws43b_layout_settings.cpp"),
            str(tmp / "harness.cpp"),
        ]
        proc = subprocess.run(
            compile_cmd, capture_output=True, text=True, cwd=str(tmp)
        )
        if proc.returncode != 0:
            cls._compile_failed = True
            cls._compile_error = proc.stderr
        else:
            cls._compile_failed = False

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_scenario(self, scenario):
        if self._compile_failed:
            self.fail(
                "C++ module failed to compile; clang++ stderr:\n"
                + self._compile_error
            )
        proc = subprocess.run(
            [str(self.binary), scenario], capture_output=True, text=True
        )
        if proc.returncode != 0:
            self.fail(
                f"scenario '{scenario}' exited with code {proc.returncode}; "
                f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
            )
        return parse_report(proc.stdout), proc.stdout

    def test_1_missing_or_corrupt_record_falls_back_to_standard(self):
        for scenario in ("missing_record", "corrupt_record", "read_begin_fails"):
            report, _ = self.run_scenario(scenario)
            self.assertEqual(report["minimal"], "0", scenario)
            self.assertEqual(report["revision"], "0", scenario)
            # No writes to NVS on fallback.
            self.assertEqual(report["put_calls"], "0", scenario)

    def test_2_reads_0x0100_and_0x0101_correctly(self):
        report, _ = self.run_scenario("read_values")
        self.assertEqual(report["standard_minimal"], "0")
        self.assertEqual(report["minimalist_minimal"], "1")
        self.assertEqual(report["minimal"], "1")
        self.assertEqual(report["revision"], "0")

    def test_3_round_trip_minimalist_and_standard(self):
        for scenario, record, expected_minimal in (
            ("round_trip_minimalist", "257", "1"),  # 0x0101
            ("round_trip_standard", "256", "0"),    # 0x0100
        ):
            report, _ = self.run_scenario(scenario)
            save_key = (
                "save_minimal_ok"
                if scenario == "round_trip_minimalist"
                else "save_standard_ok"
            )
            self.assertEqual(report[save_key], "1", scenario)
            self.assertEqual(report["record_after_save"], record, scenario)
            self.assertEqual(report["minimal_after_reload"], expected_minimal,
                             scenario)
            self.assertEqual(report["nvs_w43_layout"], record, scenario)

    def test_4_load_resets_nonzero_revision(self):
        report, _ = self.run_scenario("load_resets_revision")
        self.assertEqual(report["save_ok"], "1")
        self.assertEqual(report["revision_before_load"], "1")
        self.assertEqual(report["revision_after_load"], "0")

    def test_5_saving_current_value_does_not_open_nvs(self):
        report, _ = self.run_scenario("save_same_value_no_nvs")
        self.assertEqual(report["save_ok"], "1")
        self.assertEqual(report["extra_begin_calls"], "0")
        self.assertEqual(report["extra_put_calls"], "0")
        self.assertEqual(report["revision_after_same_save"], "0")
        self.assertEqual(report["revision_delta"], "0")

    def test_6_successful_change_increments_revision_exactly_once(self):
        report, _ = self.run_scenario("revision_increments_once")
        self.assertEqual(report["save_ok"], "1")
        self.assertEqual(report["revision_delta"], "1")

    def test_7_get_failure_falls_back_to_standard_without_writes(self):
        report, _ = self.run_scenario("get_failure_falls_back_to_standard")
        self.assertEqual(report["minimal_after_get_failure"], "0")
        self.assertEqual(report["revision_after_get_failure"], "0")
        # No *new* writes were issued by the failing load (the earlier
        # Minimalist -> Standard save legitimately wrote once).
        self.assertEqual(report["extra_puts_after_get_failure"], "0")
        self.assertEqual(report["extra_begins_after_get_failure"], "1")
        self.assertEqual(report["extra_ends_after_get_failure"], "1")
        # The earlier Standard save persisted 0x0100; the failing load keeps it.
        self.assertEqual(report["record_after_get_failure"], "256")  # 0x0100

    def test_8_begin_and_put_failures_return_false_and_preserve_state(self):
        report, _ = self.run_scenario("begin_put_fail_preserves_state")
        self.assertEqual(report["failed_begin_return"], "0")
        self.assertEqual(report["minimal_after_failed_begin"], "0")
        self.assertEqual(report["revision_after_failed_begin"], "1")
        self.assertEqual(report["failed_put0_return"], "0")
        self.assertEqual(report["minimal_after_failed_put0"], "0")
        self.assertEqual(report["revision_after_failed_put0"], "1")
        self.assertEqual(report["end_after_put0"], "1")
        self.assertEqual(report["record_after_put0"], "256")  # 0x0100, unchanged
        self.assertEqual(report["failed_put1_return"], "0")
        self.assertEqual(report["minimal_after_failed_put1"], "0")
        self.assertEqual(report["revision_after_failed_put1"], "1")
        self.assertEqual(report["end_after_put1"], "1")
        self.assertEqual(report["record_after_put1"], "256")  # 0x0100, unchanged

    def test_9_load_is_read_only_save_is_read_write_end_after_each_begin(self):
        report, _ = self.run_scenario("read_only_then_read_write")
        self.assertEqual(report["save_ok"], "1")
        self.assertEqual(report["begin_calls"], "2")
        self.assertEqual(report["end_calls"], "2")
        self.assertEqual(report["begin_read_only_flags"], "true,false")
        self.assertEqual(report["begin_read_only_0"], "true")
        self.assertEqual(report["begin_read_only_1"], "false")

    def test_10_other_nvs_keys_are_not_modified(self):
        report, _ = self.run_scenario("other_keys_untouched")
        self.assertEqual(report["save_ok"], "1")
        self.assertEqual(report["other_a"], "4660")   # 0x1234
        self.assertEqual(report["other_b"], "22136")  # 0x5678
        self.assertEqual(report["nvs_other_keys"], "2")


if __name__ == "__main__":
    unittest.main()
