#!/usr/bin/env python3

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

try:
    from kaggle.api.kaggle_api_extended import KaggleApi
except ImportError:
    KaggleApi = None


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}


def parse_frame_ranges(spec: str) -> set[int]:
    """Parse a string like "1-120,6-30,45" into a set of integer frame indices."""
    if not spec:
        raise ValueError("Empty frame range specification")

    indices: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            try:
                start = int(start_str)
                end = int(end_str)
            except ValueError as exc:
                raise ValueError(f"Invalid range component: '{part}'") from exc
            if start <= 0 or end <= 0:
                raise ValueError("Frame indices must be positive integers")
            if end < start:
                start, end = end, start
            indices.update(range(start, end + 1))
        else:
            try:
                value = int(part)
            except ValueError as exc:
                raise ValueError(f"Invalid frame index: '{part}'") from exc
            if value <= 0:
                raise ValueError("Frame indices must be positive integers")
            indices.add(value)
    if not indices:
        raise ValueError("No valid frame indices parsed from specification")
    return indices


def extract_frame_index_from_name(name: str) -> int | None:
    """Extract a frame index from a filename by taking the last integer in the stem.

    Examples:
      frame_000123.png -> 123
      fortnite_42.jpg  -> 42
    """
    stem = Path(name).stem
    numbers = re.findall(r"\d+", stem)
    if not numbers:
        return None
    return int(numbers[-1])


def build_index_to_files(root: Path) -> dict[int, list[Path]]:
    """Walk `root` recursively and map frame indices to image files."""
    mapping: dict[int, list[Path]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        idx = extract_frame_index_from_name(path.name)
        if idx is None:
            continue
        mapping.setdefault(idx, []).append(path)
    return mapping


def download_dataset(dataset: str, download_dir: Path) -> None:
    if KaggleApi is None:
        print(
            "Error: The 'kaggle' package is not installed. Install it with 'pip install kaggle' and configure your API token.",
            file=sys.stderr,
        )
        sys.exit(1)

    api = KaggleApi()
    try:
        api.authenticate()
    except Exception as exc:  # noqa: BLE001
        print("Failed to authenticate with Kaggle API.", file=sys.stderr)
        print(
            "Make sure you have 'kaggle.json' in ~/.kaggle or have set KAGGLE_USERNAME and KAGGLE_KEY.",
            file=sys.stderr,
        )
        print(f"Underlying error: {exc}", file=sys.stderr)
        sys.exit(1)

    download_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading dataset '{dataset}' to '{download_dir}' (unzip=True)...")
    api.dataset_download_files(dataset, path=str(download_dir), unzip=True)
    print("Download and unzip completed.")


def select_and_copy_frames(
    index_to_files: dict[int, list[Path]],
    desired_indices: set[int],
    output_dir: Path,
) -> tuple[int, list[int]]:
    output_dir.mkdir(parents=True, exist_ok=True)

    missing: list[int] = []
    copied = 0

    for idx in sorted(desired_indices):
        files = index_to_files.get(idx)
        if not files:
            missing.append(idx)
            continue

        for j, src in enumerate(files, start=1):
            if len(files) == 1:
                dst_name = src.name
            else:
                dst_name = f"{src.stem}_dup{j}{src.suffix}"
            dst = output_dir / dst_name
            shutil.copy2(src, dst)
            copied += 1

    return copied, missing


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download the 'cloud-gaming-captured-screen-dataset' from Kaggle and "
            "copy only a specified set of frame indices into an output directory."
        )
    )

    parser.add_argument(
        "--dataset",
        default="alirezashz/cloud-gaming-captured-screen-dataset",
        help=(
            "Kaggle dataset identifier (owner/dataset-name). "
            "Default: alirezashz/cloud-gaming-captured-screen-dataset"
        ),
    )
    parser.add_argument(
        "--download-dir",
        default="./kaggle_cloud_gaming_dataset",
        help="Directory where the full Kaggle dataset will be downloaded and unzipped.",
    )
    parser.add_argument(
        "--frames",
        required=True,
        help=(
            "Frame indices to extract, e.g. '1-120,6-30,45'. "
            "Ranges are inclusive; multiple ranges/indices can be comma-separated."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where the selected frame images will be copied.",
    )

    args = parser.parse_args(argv)

    try:
        desired_indices = parse_frame_ranges(args.frames)
    except ValueError as exc:
        print(f"Error parsing --frames: {exc}", file=sys.stderr)
        sys.exit(1)

    download_dir = Path(args.download_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    print(f"Using download directory: {download_dir}")
    print(f"Using output directory:   {output_dir}")
    print(f"Requested {len(desired_indices)} unique frame indices.")

    # Always (re)ensure dataset is available; Kaggle API will reuse files as appropriate.
    download_dataset(args.dataset, download_dir)

    print("Indexing image files by frame index...")
    index_to_files = build_index_to_files(download_dir)
    print(f"Found {len(index_to_files)} distinct frame indices across dataset images.")

    copied, missing = select_and_copy_frames(index_to_files, desired_indices, output_dir)

    print(f"Copied {copied} image file(s) into '{output_dir}'.")
    if missing:
        print(
            f"Warning: {len(missing)} requested frame indices were not found in any image filenames:",
            ", ".join(str(m) for m in missing),
            file=sys.stderr,
        )


if __name__ == "__main__":  # pragma: no cover
    main()
