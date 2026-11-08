"""Keeps AGENTS.md usable by agents: CLAUDE.md imports it, it is versioned, and
every repo path and command it names still exists (see "Keeping this guide working")."""

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GUIDE = ROOT / "AGENTS.md"

# Backticked tokens that look like repo paths: contain "/" or end with a known extension.
# Tokens starting with "/" are panel HTTP endpoints, not repo paths.
PATH_TOKEN = re.compile(r"`([A-Za-z0-9_.{},*/-]+)`")
EXTENSIONS = (".py", ".md", ".ini", ".toml", ".json", ".h", ".cpp", ".js", ".csv")


def expand(token):
    """`locale/{pl,de}.json` -> two paths; `src/*ws43b*` stays a glob."""
    m = re.search(r"\{([^}]*)\}", token)
    if not m:
        return [token]
    return [token[: m.start()] + part + token[m.end() :] for part in m.group(1).split(",")]


def resolve(token):
    """Return True if the token names something that exists in the repo."""
    for candidate in expand(token.rstrip("/")):
        if "*" in candidate:
            if not list(ROOT.glob(candidate)):
                return False
            continue
        bases = [ROOT, ROOT / "bringup/waveshare43b/integration"]
        if not any((base / candidate).exists() for base in bases):
            return False
    return True


class AgentGuide(unittest.TestCase):
    def test_claude_md_imports_agents_md(self):
        self.assertEqual((ROOT / "CLAUDE.md").read_text().strip(), "@AGENTS.md")

    def test_guide_files_are_not_git_ignored(self):
        for name in ("AGENTS.md", "CLAUDE.md"):
            result = subprocess.run(
                ["git", "check-ignore", "-q", "--no-index", name], cwd=ROOT, capture_output=True
            )
            if result.returncode == 128:
                self.skipTest("not a git checkout")
            self.assertEqual(result.returncode, 1, f"{name} is git-ignored (check .gitignore)")

    def test_named_paths_exist(self):
        text = GUIDE.read_text()
        missing = []
        for token in sorted(set(PATH_TOKEN.findall(text))):
            looks_like_path = "/" in token or token.endswith(EXTENSIONS)
            if not looks_like_path or token.startswith(("http", "-", "/")) or "..." in token:
                continue
            # Name patterns and branch names, not paths.
            if token.startswith("test_") or token in (
                "feature/",
                "backup/",
                "ws43b/layout-settings",
            ):
                continue
            if not resolve(token):
                missing.append(token)
        self.assertEqual(missing, [], "AGENTS.md names paths that do not exist")

    def test_commands_reference_existing_scripts(self):
        text = GUIDE.read_text()
        scripts = set(re.findall(r"python3 -B ([\w/.-]+\.py)", text))
        self.assertIn("scripts/agent_check.py", scripts)
        for script in scripts:
            self.assertTrue((ROOT / script).is_file(), script)


if __name__ == "__main__":
    unittest.main()
