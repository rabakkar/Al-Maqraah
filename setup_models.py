from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from huggingface_hub import snapshot_download


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MUAALEM_REPO_ID = "obadx/muaalem-model-v3_2"
DEFAULT_WHISPER_REPO_ID = "tarteel-ai/whisper-base-ar-quran"


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str
    repo_id: str
    output_dir: Path
    required_files: tuple[str, ...]
    required_any: tuple[tuple[str, ...], ...] = ()


def build_model_specs(args: argparse.Namespace) -> list[ModelSpec]:
    specs: list[ModelSpec] = []

    if not args.skip_muaalem:
        specs.append(
            ModelSpec(
                key="muaalem",
                label="Muaalem phonetic model",
                repo_id=args.muaalem_repo_id,
                output_dir=PROJECT_ROOT / "muaalem-model-v3_2",
                required_files=(
                    "config.json",
                    "preprocessor_config.json",
                    "vocab.json",
                ),
                required_any=(("model.safetensors", "pytorch_model.bin"),),
            )
        )

    if not args.skip_whisper:
        specs.append(
            ModelSpec(
                key="whisper",
                label="Quran Whisper transcription model",
                repo_id=args.whisper_repo_id,
                output_dir=PROJECT_ROOT / "whisper-quran",
                required_files=(
                    "config.json",
                    "preprocessor_config.json",
                    "tokenizer_config.json",
                ),
                required_any=(
                    ("model.safetensors", "pytorch_model.bin"),
                    ("tokenizer.json", "vocab.json"),
                ),
            )
        )

    return specs


def missing_requirements(spec: ModelSpec) -> list[str]:
    missing = [
        filename
        for filename in spec.required_files
        if not (spec.output_dir / filename).is_file()
    ]

    for alternatives in spec.required_any:
        if not any((spec.output_dir / filename).is_file() for filename in alternatives):
            missing.append("one of: " + ", ".join(alternatives))

    return missing


def download_snapshot(
    spec: ModelSpec,
    token: str | None,
    cache_dir: Path | None,
) -> str:
    kwargs = {
        "repo_id": spec.repo_id,
        "local_dir": str(spec.output_dir),
        "token": token,
    }
    if cache_dir is not None:
        kwargs["cache_dir"] = str(cache_dir)

    attempts = (
        {"local_dir_use_symlinks": False, "resume_download": True},
        {"resume_download": True},
        {},
    )

    last_error: TypeError | None = None
    for extra_kwargs in attempts:
        try:
            return str(snapshot_download(**kwargs, **extra_kwargs))
        except TypeError as exc:
            last_error = exc

    raise last_error or RuntimeError("Unable to call snapshot_download")


def ensure_model(
    spec: ModelSpec,
    token: str | None,
    cache_dir: Path | None,
    force: bool,
    dry_run: bool,
) -> bool:
    spec.output_dir.mkdir(parents=True, exist_ok=True)
    missing_before = missing_requirements(spec)

    if not force and not missing_before:
        print(f"[ok] {spec.label} already exists: {spec.output_dir}")
        return True

    if missing_before:
        print(f"[info] {spec.label} is missing {format_missing(missing_before)}")
    elif force:
        print(f"[info] Force download requested for {spec.label}")

    print(f"[download] {spec.repo_id} -> {spec.output_dir}")
    if dry_run:
        print("[dry-run] Download skipped.")
        return not missing_before

    try:
        local_path = download_snapshot(spec, token=token, cache_dir=cache_dir)
    except Exception as exc:
        print(f"[error] Failed to download {spec.repo_id}: {exc}", file=sys.stderr)
        return False

    print(f"[done] Downloaded to: {local_path}")

    missing_after = missing_requirements(spec)
    if missing_after:
        print(
            f"[error] {spec.label} is still missing {format_missing(missing_after)}",
            file=sys.stderr,
        )
        return False

    print(f"[ok] {spec.label} is ready.")
    return True


def format_missing(items: Iterable[str]) -> str:
    return ", ".join(items)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the local model folders and download the models required by the app.",
    )
    parser.add_argument(
        "--muaalem-repo-id",
        default=os.environ.get("MUAALEM_REPO_ID", DEFAULT_MUAALEM_REPO_ID),
        help="Hugging Face repo id for the Muaalem phonetic model.",
    )
    parser.add_argument(
        "--whisper-repo-id",
        default=os.environ.get("WHISPER_QURAN_REPO_ID", DEFAULT_WHISPER_REPO_ID),
        help="Hugging Face repo id for the Quran Whisper transcription model.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("HF_TOKEN"),
        help="Optional Hugging Face token. You can also set HF_TOKEN.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Optional Hugging Face cache directory.",
    )
    parser.add_argument(
        "--skip-muaalem",
        action="store_true",
        help="Skip downloading the Muaalem phonetic model.",
    )
    parser.add_argument(
        "--skip-whisper",
        action="store_true",
        help="Skip downloading the Quran Whisper transcription model.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Download again even if the required files already exist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without downloading files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = build_model_specs(args)

    if not specs:
        print("[info] No models selected.")
        return 0

    all_ready = True
    for spec in specs:
        ready = ensure_model(
            spec,
            token=args.token,
            cache_dir=args.cache_dir,
            force=args.force,
            dry_run=args.dry_run,
        )
        all_ready = all_ready and ready

    if all_ready:
        print("\nAll selected models are ready.")
        print("Next step: python app.py")
        return 0

    print("\nSome models are not ready. Fix the errors above, then run this file again.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
