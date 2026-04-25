from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
)
BINARY_SUFFIXES = {
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pyc",
    ".webp",
    ".xls",
    ".xlsx",
}


class SecretHygieneTests(unittest.TestCase):
    def test_tracked_files_do_not_contain_literal_api_keys(self):
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-files"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

        offenders = []
        tracked_files = result.stdout.decode("utf-8", errors="ignore").splitlines()
        for relative_path in tracked_files:
            path = PROJECT_ROOT / relative_path
            if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                offenders.append(relative_path)

        self.assertEqual([], offenders, "Tracked files contain possible literal API keys.")


if __name__ == "__main__":
    unittest.main()
