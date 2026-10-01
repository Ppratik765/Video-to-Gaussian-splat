"""
Cross-platform task runner for splat360 development.
Usage: python tasks.py <command>
Commands:
  test      Run pytest
  lint      Run ruff check
  typecheck Run mypy
  format    Run ruff format
  all       Run format, lint, typecheck, and test
"""

import subprocess
import sys


def run(cmd):
    print(f"--> {' '.join(cmd)}")
    res = subprocess.run(cmd)
    if res.returncode != 0:
        sys.exit(res.returncode)

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "test":
        run([sys.executable, "-m", "pytest", "tests/unit", "-v"])
    elif cmd == "lint":
        run([sys.executable, "-m", "ruff", "check", "."])
    elif cmd == "typecheck":
        run([sys.executable, "-m", "mypy", "src"])
    elif cmd == "format":
        run([sys.executable, "-m", "ruff", "format", "."])
    elif cmd == "all":
        run([sys.executable, "-m", "ruff", "format", "."])
        run([sys.executable, "-m", "ruff", "check", "."])
        run([sys.executable, "-m", "mypy", "src"])
        run([sys.executable, "-m", "pytest", "tests/unit", "-v"])
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
