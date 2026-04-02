"""Environment and runtime diagnostics for CLI and tests."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass

from .compat import HELLO_AGENTS_AVAILABLE


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def _check_import(module_name: str) -> DoctorCheck:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        return DoctorCheck(name=module_name, ok=False, detail=str(exc))
    return DoctorCheck(name=module_name, ok=True, detail="ok")


def run_doctor() -> tuple[DoctorCheck, ...]:
    return (
        DoctorCheck("hello_agents", HELLO_AGENTS_AVAILABLE, "ok" if HELLO_AGENTS_AVAILABLE else "missing"),
        _check_import("rich"),
        _check_import("gradio"),
        _check_import("pdfplumber"),
        DoctorCheck(
            "tavily_env",
            bool(os.getenv("TAVILY_API_KEY")),
            "configured" if os.getenv("TAVILY_API_KEY") else "missing",
        ),
        DoctorCheck(
            "vision_env",
            all(os.getenv(name) for name in ("VISION_LLM_MODEL_ID", "VISION_LLM_API_KEY", "VISION_LLM_BASE_URL")),
            "configured"
            if all(os.getenv(name) for name in ("VISION_LLM_MODEL_ID", "VISION_LLM_API_KEY", "VISION_LLM_BASE_URL"))
            else "missing",
        ),
    )
