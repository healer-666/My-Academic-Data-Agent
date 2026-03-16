from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.config import RuntimeConfig
from data_analysis_agent.reporting import ReportTelemetry
from data_analysis_agent.vision_review import (
    prepare_image_for_vision,
    run_visual_review,
    select_visual_review_candidates,
)


class VisionReviewTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"vision_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _make_png(self, path: Path, size: tuple[int, int]) -> None:
        from PIL import Image

        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color=(120, 160, 210)).save(path, format="PNG")

    def test_prepare_image_for_vision_resizes_large_png_to_jpeg_payload(self):
        case_dir = self._workspace_case_dir()
        image_path = case_dir / "large.png"
        self._make_png(image_path, (2400, 1600))

        prepared = prepare_image_for_vision(image_path, alt_text="Large chart", max_image_side=1024)

        self.assertEqual(prepared.original_size, (2400, 1600))
        self.assertLessEqual(max(prepared.resized_size), 1024)
        self.assertEqual(prepared.media_type, "image/jpeg")
        self.assertGreater(prepared.output_bytes, 0)
        self.assertTrue(prepared.encoded_image)

    def test_select_visual_review_candidates_skips_svg_and_enforces_limit(self):
        case_dir = self._workspace_case_dir()
        run_dir = case_dir / "run_demo"
        review_dir = run_dir / "figures" / "review_round_1"
        self._make_png(review_dir / "a.png", (400, 300))
        self._make_png(review_dir / "b.jpg", (400, 300))
        self._make_png(review_dir / "c.jpeg", (400, 300))
        self._make_png(review_dir / "d.png", (400, 300))
        (review_dir / "e.svg").write_text("<svg></svg>", encoding="utf-8")

        report_markdown = (
            "![A](figures/review_round_1/a.png)\n"
            "![B](figures/review_round_1/b.jpg)\n"
            "![C](figures/review_round_1/c.jpeg)\n"
            "![D](figures/review_round_1/d.png)\n"
            "![E](figures/review_round_1/e.svg)\n"
        )
        telemetry = ReportTelemetry(
            figures_generated=(
                (review_dir / "a.png").as_posix(),
                (review_dir / "b.jpg").as_posix(),
                (review_dir / "c.jpeg").as_posix(),
                (review_dir / "d.png").as_posix(),
                (review_dir / "e.svg").as_posix(),
            )
        )

        selected, skipped = select_visual_review_candidates(
            report_markdown=report_markdown,
            telemetry=telemetry,
            run_dir=run_dir,
            review_round=1,
            max_images=3,
        )

        self.assertEqual(len(selected), 3)
        self.assertTrue(any("unsupported_suffix:.svg" in item for item in skipped))
        self.assertTrue(any("omitted_due_to_limit" in item for item in skipped))

    def test_run_visual_review_returns_unavailable_when_config_missing(self):
        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
        )

        result = run_visual_review(
            runtime_config=runtime_config,
            report_markdown="![Chart](outputs/run_demo/figures/review_round_1/chart.png)",
            telemetry=ReportTelemetry(figures_generated=("outputs/run_demo/figures/review_round_1/chart.png",)),
            run_dir=PROJECT_ROOT,
            review_round=1,
        )

        self.assertEqual(result.status, "unavailable")
        self.assertIn("未启用", result.summary)


if __name__ == "__main__":
    unittest.main()
