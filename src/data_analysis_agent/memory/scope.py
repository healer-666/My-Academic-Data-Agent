"""Helpers for stable project-level memory scopes."""

from __future__ import annotations

import re
from pathlib import Path


def normalize_memory_scope_label(value: str | None) -> str:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", str(value or "").strip()).strip("-")
    return normalized.lower() or ""


def derive_memory_scope_key(
    *,
    explicit_scope_key: str | None = None,
    session_label: str | None = None,
    source_path: str | Path | None = None,
) -> str:
    for candidate in (explicit_scope_key, session_label):
        normalized = normalize_memory_scope_label(candidate)
        if normalized:
            return normalized
    if source_path not in (None, ""):
        normalized = normalize_memory_scope_label(Path(str(source_path)).stem)
        if normalized:
            return normalized
    return "project-default"
