#include "ws43b_idle_policy.h"

#include <cstdint>
#include <cstdlib>
#include <iostream>

namespace {
unsigned checks = 0;

void expect(bool condition, const char *message) {
  ++checks;
  if (!condition) {
    std::cerr << "FAIL: " << message << '\n';
    std::exit(1);
  }
}

void enteringIdle() {
  ws43b_view::IdlePolicy policy;
  expect(!policy.update(0, false, 1, 0), "setup cannot expire");
  expect(!policy.update(3600000, false, 1, 0), "time while in setup does not count");
  expect(!policy.update(3600100, true, 1, 0), "leaving setup begins a full interval");
  expect(!policy.update(3660099, true, 1, 0), "idle interval has not elapsed early");
  expect(policy.update(3660100, true, 1, 0), "idle expires at the configured boundary");
  expect(policy.update(3700000, true, 1, 0), "idle stays expired without activity");
}

void userActivity() {
  ws43b_view::IdlePolicy policy;
  expect(!policy.update(0, true, 1, 1), "time zero is a valid eligible start");
  policy.activity(59000);
  expect(!policy.update(60000, true, 1, 1), "touch postpones imminent expiry");
  expect(!policy.update(118999, true, 1, 1), "touch restarts a full interval");
  expect(policy.update(119000, true, 1, 1), "expiry follows the last activity");
  policy.activity(120000);
  expect(!policy.update(120000, true, 1, 1), "touch wakes an expired display");
  expect(!policy.update(179999, true, 1, 1), "wake gives a complete new interval");
  expect(policy.update(180000, true, 1, 1), "display may expire again after wake");
}

void settingsAndEligibility() {
  ws43b_view::IdlePolicy policy;
  policy.update(100, true, 1, 8);
  expect(policy.update(60100, true, 1, 8), "setup expires display");
  expect(!policy.update(60101, true, 1, 9), "settings revision wakes display");
  expect(!policy.update(120100, true, 1, 9), "revision gives a full interval");
  expect(policy.update(120101, true, 1, 9), "new revision eventually expires");
  expect(!policy.update(120102, false, 1, 9), "entering setup immediately wakes");
  policy.activity(150000);
  expect(!policy.update(500000, true, 1, 9), "leaving setup starts a new interval");
  expect(!policy.update(559999, true, 1, 9), "setup time and earlier touch do not count");
  expect(policy.update(560000, true, 1, 9), "configured state gets a complete interval");
  expect(!policy.update(560001, true, 5, 9), "changed duration also resets without a revision");
  expect(!policy.update(860000, true, 5, 9), "changed duration applies its full interval");
  expect(policy.update(860001, true, 5, 9), "changed duration expires at five minutes");
}

void disablingAndWrap() {
  ws43b_view::IdlePolicy policy;
  policy.activity(0);
  expect(!policy.update(0, true, 0, 0), "zero minutes disables expiry");
  expect(!policy.update(UINT32_MAX, true, 0, 0), "disabled stays awake indefinitely");
  constexpr uint32_t start = UINT32_MAX - 30000u;
  expect(!policy.update(start, true, 1, 1), "enabling near wrap starts awake");
  expect(!policy.update(uint32_t(start + 59999u), true, 1, 1), "wrap does not expire early");
  expect(policy.update(uint32_t(start + 60000u), true, 1, 1), "expiry works across wrap");
  expect(policy.update(start, true, 1, 1), "expiry remains latched across a later clock cycle");
  expect(!policy.update(start, true, 0, 2), "disabling wakes an expired display");
  expect(!policy.update(1000, true, 1, 3), "reenabling starts a complete interval");
  expect(!policy.update(60999, true, 1, 3), "disabled time is excluded");
  expect(policy.update(61000, true, 1, 3), "reenabled interval expires normally");
}
} // namespace

int main() {
  enteringIdle();
  userActivity();
  settingsAndEligibility();
  disablingAndWrap();
  std::cout << "PASS: " << checks << " native idle-policy checks; hardware unverified\n";
}
