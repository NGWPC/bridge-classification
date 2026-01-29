"""
Split silver_training bridge data into fixed 70/15/15 train/validation/test by HUC.

Reads HUC-organized .laz files from silver_training, shuffles bridges per HUC with
a fixed seed, assigns ~70% train, ~15% val, ~15% test, and writes split directories
plus ID manifests (including test IDs for human annotators).

Usage:
    python utils/split_data.py
    python utils/split_data.py --input-dir ./data/ml-data/silver_training --output-dir ./data/ml-data --seed 42
    python utils/split_data.py --symlink
    python utils/split_data.py --train-ratio 0.8 --val-ratio 0.1
    python utils/split_data.py --train-ratio 0.7 --test-ratio 0.2
"""

import argparse
import json
import random
import shutil
from pathlib import Path
from typing import Dict, List, Tuple


SPLIT_NAMES = ("training", "validation", "testing")


def discover_bridges_by_huc(input_dir: Path) -> Dict[str, List[Path]]:
    """
    Discover all .laz bridge files grouped by huc_id.

    Returns:
        Dict mapping huc_id -> list of Path to .laz files (each file stem = bridge ID).
    """
    huc_bridges: Dict[str, List[Path]] = {}
    for child in sorted(input_dir.iterdir()):
        if not child.is_dir():
            continue
        huc_id = child.name
        laz_files = list(child.glob("*.laz"))
        if not laz_files:
            continue
        huc_bridges[huc_id] = sorted(laz_files)
    return huc_bridges


def assign_splits(
    huc_bridges: Dict[str, List[Path]],
    seed: int,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]], List[Tuple[str, str]]]:
    """
    For each HUC, shuffle bridges with seed and assign train_ratio/val_ratio/test_ratio.

    Returns:
        (train_list, val_list, test_list) where each list contains (huc_id, bridge_stem).
    """
    rng = random.Random(seed)
    train_ids: List[Tuple[str, str]] = []
    val_ids: List[Tuple[str, str]] = []
    test_ids: List[Tuple[str, str]] = []

    for huc_id, laz_paths in huc_bridges.items():
        bridges = [p.stem for p in laz_paths]
        rng.shuffle(bridges)
        n = len(bridges)
        n_train = int(train_ratio * n)
        n_val = int(val_ratio * n)
        n_test = n - n_train - n_val

        i = 0
        for _ in range(n_train):
            train_ids.append((huc_id, bridges[i]))
            i += 1
        for _ in range(n_val):
            val_ids.append((huc_id, bridges[i]))
            i += 1
        for _ in range(n_test):
            test_ids.append((huc_id, bridges[i]))
            i += 1

    return train_ids, val_ids, test_ids


def write_split_dirs(
    input_dir: Path,
    output_dir: Path,
    train_ids: List[Tuple[str, str]],
    val_ids: List[Tuple[str, str]],
    test_ids: List[Tuple[str, str]],
    use_symlink: bool,
) -> None:
    """Create training/, validation/, testing/ under output_dir and copy or symlink .laz files."""
    split_to_ids = {
        "training": train_ids,
        "validation": val_ids,
        "testing": test_ids,
    }
    for split_name, id_list in split_to_ids.items():
        split_dir = output_dir / split_name
        for huc_id, bridge_stem in id_list:
            src = input_dir / huc_id / f"{bridge_stem}.laz"
            dst_dir = split_dir / huc_id
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / f"{bridge_stem}.laz"
            if use_symlink:
                if dst.exists():
                    dst.unlink()
                dst.symlink_to(src.resolve())
            else:
                shutil.copy2(src, dst, follow_symlinks=True)


def write_manifests(
    output_dir: Path,
    train_ids: List[Tuple[str, str]],
    val_ids: List[Tuple[str, str]],
    test_ids: List[Tuple[str, str]],
) -> None:
    """Write split_*_ids.txt and split_manifest.json under output_dir."""
    # Text files: one line per bridge, format huc_id/bridge_stem
    for name, id_list in (
        ("split_train_ids.txt", train_ids),
        ("split_val_ids.txt", val_ids),
        ("split_test_ids.txt", test_ids),
    ):
        path = output_dir / name
        with open(path, "w") as f:
            for huc_id, bridge_stem in id_list:
                f.write(f"{huc_id}/{bridge_stem}\n")

    # JSON manifest for programmatic use
    manifest = {
        "train": [{"huc_id": h, "bridge_stem": b} for h, b in train_ids],
        "val": [{"huc_id": h, "bridge_stem": b} for h, b in val_ids],
        "test": [{"huc_id": h, "bridge_stem": b} for h, b in test_ids],
    }
    with open(output_dir / "split_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split silver_training bridge data into 70/15/15 train/validation/test by HUC (reproducible with seed)."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("./data/ml-data/silver_training"),
        help="Input directory containing HUC-organized .laz files (default: ./data/ml-data/silver_training)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./data/ml-data"),
        help="Output base directory for training/, validation/, testing/ and manifest files (default: ./data/ml-data)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=27,
        help="Random seed for reproducible split (default: 42)",
    )
    parser.add_argument(
        "--symlink",
        action="store_true",
        help="Create symlinks instead of copying .laz files (saves disk space)",
    )
    parser.add_argument(
        "--train-ratio",
        type=float,
        default=None,
        help="Train split ratio in (0, 1). At least two of --train-ratio, --val-ratio, --test-ratio must be set; the third is computed as 1 minus the sum of the other two (default: 0.70 if none set).",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=None,
        help="Validation split ratio in (0, 1). At least two of --train-ratio, --val-ratio, --test-ratio must be set (default: 0.15 if none set).",
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=None,
        help="Test split ratio in (0, 1). At least two of --train-ratio, --val-ratio, --test-ratio must be set (default: 0.15 if none set).",
    )
    args = parser.parse_args()

    # Resolve and validate train/val/test ratios
    provided = sum(1 for r in (args.train_ratio, args.val_ratio, args.test_ratio) if r is not None)
    if provided == 0 or provided == 1:
        train_ratio, val_ratio, test_ratio = 0.70, 0.15, 0.15
    elif provided == 2:
        given_sum = (args.train_ratio or 0) + (args.val_ratio or 0) + (args.test_ratio or 0)
        # Fill the one missing
        if args.train_ratio is None:
            train_ratio = 1.0 - given_sum
            val_ratio = args.val_ratio
            test_ratio = args.test_ratio
        elif args.val_ratio is None:
            train_ratio = args.train_ratio
            val_ratio = 1.0 - given_sum
            test_ratio = args.test_ratio
        else:
            train_ratio = args.train_ratio
            val_ratio = args.val_ratio
            test_ratio = 1.0 - given_sum
        if not (0 <= train_ratio <= 1 and 0 <= val_ratio <= 1 and 0 <= test_ratio <= 1):
            raise SystemExit(
                f"Error: Computed ratio out of [0, 1]. train={train_ratio}, val={val_ratio}, test={test_ratio}"
            )
    else:
        train_ratio = args.train_ratio
        val_ratio = args.val_ratio
        test_ratio = args.test_ratio
        if abs(train_ratio + val_ratio + test_ratio - 1.0) >= 1e-6:
            raise SystemExit(
                f"Error: --train-ratio, --val-ratio, --test-ratio must sum to 1.0 (got {train_ratio + val_ratio + test_ratio})"
            )
    for name, r in (("train", train_ratio), ("val", val_ratio), ("test", test_ratio)):
        if not (0 <= r <= 1):
            raise SystemExit(f"Error: {name} ratio must be in [0, 1], got {r}")

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()

    if not input_dir.exists():
        raise SystemExit(f"Error: Input directory does not exist: {input_dir}")

    huc_bridges = discover_bridges_by_huc(input_dir)
    if not huc_bridges:
        raise SystemExit(f"No HUC directories with .laz files found in {input_dir}")

    total_bridges = sum(len(pths) for pths in huc_bridges.values())
    print(f"Found {len(huc_bridges)} HUC(s) with {total_bridges} bridge(s) in {input_dir}")

    train_ids, val_ids, test_ids = assign_splits(
        huc_bridges, args.seed, train_ratio, val_ratio, test_ratio
    )
    print(
        f"Split (seed={args.seed}, ratios {train_ratio:.2f}/{val_ratio:.2f}/{test_ratio:.2f}): "
        f"train={len(train_ids)}, val={len(val_ids)}, test={len(test_ids)}"
    )

    # Warn if training, validation, or testing dirs already exist; confirm before overwriting
    existing = [s for s in SPLIT_NAMES if (output_dir / s).exists()]
    if existing:
        print(
            f"Warning: The following directories already exist under {output_dir}: {', '.join(existing)}."
        )
        reply = input("Overwrite and recreate them? [Y/n]: ").strip().lower()
        if reply in ("n", "no"):
            raise SystemExit("Aborted. No directories were modified.")
        for name in SPLIT_NAMES:
            path = output_dir / name
            if path.exists():
                shutil.rmtree(path)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_split_dirs(input_dir, output_dir, train_ids, val_ids, test_ids, args.symlink)
    print(f"Wrote {', '.join(SPLIT_NAMES)} under {output_dir}")

    write_manifests(output_dir, train_ids, val_ids, test_ids)
    print(
        f"Wrote split_train_ids.txt, split_val_ids.txt, split_test_ids.txt, split_manifest.json in {output_dir}"
    )
    print("Test IDs for human annotators: split_test_ids.txt (and split_manifest.json)")


if __name__ == "__main__":
    main()
