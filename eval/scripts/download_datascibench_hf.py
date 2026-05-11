from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO_ID = "zd21/DataSciBench"


def _resolve_path(path: str | Path, *, root: Path = PROJECT_ROOT) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def _token_from_env() -> str | None:
    for name in ("HF_TOKEN", "HUGGINGFACE_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
        value = os.getenv(name)
        if value:
            return value
    return None


def count_gt_dirs(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.rglob("gt") if path.is_dir())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download gated DataSciBench HuggingFace evaluation data.")
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument("--output-dir", default="data/external/datascibench_hf")
    parser.add_argument("--token", default=None, help="HuggingFace token. Prefer HF_TOKEN env var instead of passing this.")
    parser.add_argument("--allow-pattern", action="append", default=None)
    parser.add_argument("--max-workers", type=int, default=8)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import GatedRepoError, HfHubHTTPError
    except ImportError as exc:
        raise SystemExit("huggingface_hub is required in this environment") from exc

    output_dir = _resolve_path(args.output_dir).resolve()
    token = args.token or _token_from_env()
    try:
        path = snapshot_download(
            repo_id=args.repo_id,
            repo_type="dataset",
            local_dir=output_dir,
            token=token,
            allow_patterns=args.allow_pattern,
            max_workers=max(1, args.max_workers),
        )
    except GatedRepoError as exc:
        raise SystemExit(
            "DataSciBench HuggingFace dataset is gated. Request access on HuggingFace, then run "
            "`huggingface-cli login` or set `HF_TOKEN` before retrying.\n"
            f"Original error: {exc}"
        ) from exc
    except HfHubHTTPError as exc:
        raise SystemExit(f"HuggingFace download failed: {exc}") from exc

    gt_count = count_gt_dirs(Path(path))
    print(f"Downloaded to: {path}")
    print(f"GT directory count: {gt_count}")
    if gt_count == 0:
        print("WARNING: no `gt` directories found; verify the dataset layout before official TFC scoring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
