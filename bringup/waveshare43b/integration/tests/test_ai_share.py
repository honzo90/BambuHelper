"""AI attribution rules (AGENTS.md "Attribution"): classification and commit-msg hook."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location("ai_share", ROOT / "scripts" / "ai_share.py")
ai_share = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ai_share)


class Classify(unittest.TestCase):
    def test_ai_assisted_trailer(self):
        msg = "Fix x\n\nAI-Assisted: qwen3.6:35b\n"
        self.assertEqual(ai_share.classify(msg), ("llm", "qwen3.6:35b"))

    def test_human_trailer(self):
        self.assertEqual(ai_share.classify("Fix x\n\nAI-Assisted: none\n"), ("human", ""))

    def test_ai_co_author_trailer_any_case(self):
        for trailer in (
            "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
            "Co-authored-by: GitHub Copilot <copilot@github.com>",
        ):
            category, model = ai_share.classify(f"Fix x\n\n{trailer}\n")
            self.assertEqual(category, "llm", trailer)
            self.assertNotIn("<", model)

    def test_human_co_author_is_not_llm(self):
        msg = "Fix x\n\nCo-Authored-By: Jan Kowalski <jan@example.com>\n"
        self.assertEqual(ai_share.classify(msg), ("unknown", ""))

    def test_no_trailer_is_unknown(self):
        self.assertEqual(ai_share.classify("Fix x\n\nSome body text.\n"), ("unknown", ""))

    def test_explicit_trailer_wins_over_co_author(self):
        msg = "Fix x\n\nAI-Assisted: none\nCo-Authored-By: Claude <noreply@anthropic.com>\n"
        self.assertEqual(ai_share.classify(msg)[0], "human")


class Hook(unittest.TestCase):
    def check(self, message):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(message)
        try:
            return ai_share.check_message(f.name)
        finally:
            os.unlink(f.name)

    def test_refuses_unattributed_commit(self):
        if (ROOT / ".git" / "MERGE_HEAD").exists():
            self.skipTest("merge in progress")
        self.assertEqual(self.check("Fix x\n\nBody.\n"), 1)

    def test_comment_lines_do_not_count(self):
        if (ROOT / ".git" / "MERGE_HEAD").exists():
            self.skipTest("merge in progress")
        self.assertEqual(self.check("Fix x\n# AI-Assisted: none\n"), 1)

    def test_accepts_attributed_commit(self):
        self.assertEqual(self.check("Fix x\n\nAI-Assisted: none\n"), 0)
        self.assertEqual(self.check("Fix x\n\nAI-Assisted: Claude Opus 5.5\n"), 0)

    def test_hook_file_calls_checker(self):
        hook = ROOT / ".githooks" / "commit-msg"
        self.assertTrue(os.access(hook, os.X_OK), "hook must be executable")
        self.assertIn("scripts/ai_share.py\" --check-msg", hook.read_text())


if __name__ == "__main__":
    unittest.main()
