"""Reject common Spanish prose in project communication files.

Legacy Spanish API identifiers are compatibility contracts and are outside this
documentation-focused policy.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPLICIT_FILES = {
    ROOT / ".env.example",
    ROOT / "BACKLOG.md",
    ROOT / "CHANGELOG.md",
    ROOT / "CODE_OF_CONDUCT.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "README.md",
    ROOT / "SECURITY.md",
    ROOT / "SUPPORT.md",
}
GLOBS = ("docs/**/*.md", ".github/**/*.md", ".github/**/*.yml", ".github/**/*.yaml")
SPANISH = re.compile(
    r"[áéíóúñ¿¡]|\b(?:contraseña|documentación|descarga|papelera|pruebas|"
    r"para que|no existe|más rápido|carpeta del|servidor remoto)\b",
    re.IGNORECASE,
)
ALLOW_MARKER = "english-policy: allow"


def policy_files() -> list[Path]:
    files = {path for path in EXPLICIT_FILES if path.exists()}
    for pattern in GLOBS:
        files.update(path for path in ROOT.glob(pattern) if path.is_file())
    return sorted(files)


def violations() -> list[str]:
    found: list[str] = []
    for path in policy_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ALLOW_MARKER not in line and SPANISH.search(line):
                found.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    return found


def main() -> int:
    found = violations()
    if found:
        print("English communication policy violations:")
        print("\n".join(f"- {item}" for item in found))
        return 1
    print(f"English communication policy passed ({len(policy_files())} files checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
