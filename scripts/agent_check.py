#!/usr/bin/env python3
"""Run the 4.3B host regression tests (the pre-commit gate from AGENTS.md).

Usage:
  python3 -B scripts/agent_check.py            # all tests
  python3 -B scripts/agent_check.py -k memory  # only test_*memory*.py modules
Exit code 0 = all passed.
"""
import argparse
import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent / "bringup" / "waveshare43b" / "integration" / "tests"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-k", default="", help="substring of the test module name")
    parser.add_argument("-v", action="store_true", help="verbose test output")
    args = parser.parse_args()

    pattern = f"test_*{args.k}*.py" if args.k else "test_*.py"
    suite = unittest.defaultTestLoader.discover(str(TESTS), pattern=pattern, top_level_dir=str(TESTS))
    if suite.countTestCases() == 0:
        print(f"No tests match {pattern} in {TESTS}", file=sys.stderr)
        return 2
    result = unittest.TextTestRunner(verbosity=2 if args.v else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
