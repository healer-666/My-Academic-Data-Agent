"""Gradio-based web demo layer for Academic-Data-Agent."""

from .app import build_demo
from .service import default_max_reviews_for_quality, stream_analysis_session

__all__ = [
    "build_demo",
    "default_max_reviews_for_quality",
    "stream_analysis_session",
]
