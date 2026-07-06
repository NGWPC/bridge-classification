# Utility Scripts

Command-line tools for evaluation, data preparation, visualization, and verification.
These scripts live in `utils/` and are not importable as library modules.
Run each with `--help` for the full argument list.

!!! tip "See also"
    - [Data Pipeline](../data-pipeline.md) for how these scripts fit into the end-to-end flow
    - [AWS Batch Inference](../aws-batch-inference.md) for the batch scripts in `scripts/`

---

## Evaluation & Registry

### `utils/evaluate_model.py`

Evaluates a trained model against human-annotated (gold) data.
Reports per-class and binary metrics, compares against the silver baseline, and optionally updates the S3 model registry.

| Argument | Default | Description |
|----------|---------|-------------|
| `--gold-dir` | *(required)* | Gold (human-annotated) data directory (HUC-organized LAS/LAZ) |
| `--test-dir` | *(required)* | Test data directory with silver LAZ files |
| `--model` | None | Path to .ckpt checkpoint (required if `--inference-dir` not provided) |
| `--inference-dir` | None | Pre-computed inference output directory (skips running model) |
| `--output-dir` | `./evaluation_results` | Output directory for results |
| `--device` | `auto` | Device for inference (`cpu`, `cuda`, `auto`) |
| `--voxel-size` | 0.1 | Voxel size in meters, must match training |
| `--bridge-timeout` | 150 | Per-bridge inference timeout in seconds |
| `--no-plot` | False | Skip confusion matrix PNG generation |
| `--register` | False | Update model registry with evaluation metrics |
| `--model-name` | None | Registry model name (required with `--register`) |
| `--eval-name` | `gold-{N}` | Evaluation set name for registry key |
| `--bucket` | `my-bucket` | S3 bucket |
| `--prefix` | `bridge-classification/models` | S3 prefix |
| `--profile` | None | AWS profile name |

**Outputs:** `evaluation_metrics.json`, `per_bridge_metrics.csv`, `confusion_matrix.png`, `confusion_matrix_binary.png`

```bash
# Full evaluation with inference (GPU)
python utils/evaluate_model.py \
    --gold-dir ./data/ml-data/gold-data \
    --test-dir ./data/ml-data/testing \
    --model ./experiments/bridge-base-all-data-v3/version_0/checkpoints/best.ckpt \
    --output-dir ./evaluation_results/

# Pre-computed inference (no GPU)
python utils/evaluate_model.py \
    --gold-dir ./data/ml-data/gold-data \
    --test-dir ./data/ml-data/testing \
    --inference-dir ./evaluation_results/v3/inference_output \
    --output-dir ./evaluation_results/v3

# Evaluate and register results to S3
python utils/evaluate_model.py \
    --gold-dir ./data/ml-data/gold-data \
    --test-dir ./data/ml-data/testing \
    --inference-dir ./evaluation_results/v3/inference_output \
    --register --model-name bridge-base-all-data-v3 \
    --bucket my-bucket --prefix bridge-classification/models --profile my-profile
```

---

### `utils/compare_experiments.py`

Prints a sorted comparison table of model evaluation metrics from `registry.json`.

| Argument | Default | Description |
|----------|---------|-------------|
| `--registry` | `data/models/registry.json` | Local registry path |
| `--eval-set` | all | Evaluation set to compare |
| `--sort` | `bridge_deck_iou` | Metric to sort by (descending) |
| `--from-s3` | False | Load registry from S3 |
| `--bucket` | `my-bucket` | S3 bucket (with `--from-s3`) |
| `--prefix` | `bridge-classification/models` | S3 prefix (with `--from-s3`) |
| `--profile` | None | AWS profile name |

---

### `utils/register_model.py`

Registers a trained model to the S3-based model registry.
Uploads the best checkpoint + config files, creates lineage tracking for fine-tuned models.

| Argument | Default | Description |
|----------|---------|-------------|
| `--exp-dir` | *(required)* | Path to Lightning experiment version directory |
| `--checkpoint` | `best` | `best`, `last`, or a specific filename |
| `--name` | *(required)* | Model name for the registry |
| `--description` | *(required)* | Human-readable description |
| `--parent` | None | Parent model name (for fine-tuned models) |
| `--bucket` | *(required)* | S3 bucket |
| `--prefix` | *(required)* | S3 prefix (e.g. `bridge-classification/models`) |
| `--profile` | None | AWS profile name |

---

### `utils/promote_model.py`

Promotes a model to production in the S3 model registry.
Demotes the current production model back to "evaluated" and prints the `s3_checkpoint_uri` for updating `terraform.tfvars`.

| Argument | Default | Description |
|----------|---------|-------------|
| `--name` | *(required)* | Model name to promote |
| `--bucket` | `my-bucket` | S3 bucket |
| `--prefix` | `bridge-classification/models` | S3 prefix |
| `--profile` | None | AWS profile name |
| `--dry-run` | False | Show changes without modifying S3 |

---

## Data Preparation

### `utils/split_data.py`

Splits bridge data into train/validation/test by HUC with per-HUC bridge-level splitting.

| Argument | Default | Description |
|----------|---------|-------------|
| `--laz-dir` | `./data/ml-data/silver_training` | Source LAZ/LAS directory |
| `--npy-dir` | `./data/ml-data/silver_training_normalized` | Normalized NPY directory |
| `--output-dir` | `./data/ml-data` | Output base directory |
| `--holdout-test-ids` | None | File with fixed test IDs (`huc_id/bridge_stem` per line) |
| `--train-ratio` | 0.70 | Training split fraction |
| `--val-ratio` | 0.15 | Validation split fraction |
| `--test-ratio` | 0.15 | Test split fraction |
| `--symlink` | False | Create symlinks instead of copies |
| `--seed` | 27 | Random seed |
| `--workers` | `cpu_count` | Parallel workers |

---

### `utils/calculate_weights.py`

Computes inverse-frequency class weights from preprocessed `.json` metadata.

| Argument | Default | Description |
|----------|---------|-------------|
| `--data-dir` | `./data/ml-data/training` | Directory containing `.json` metadata files |
| `--output` | None | Output JSON file path |
| `--verbose` | False | Print raw counts and weights |
| `--workers` | 1 | Parallel workers |

---

### `utils/prepare_run.py`

Prepares a self-contained pipeline run directory from a flat bridge GeoPackage.
Splits the input into per-HUC GeoPackages matching the directory structure expected by `download_and_weak_supervise_hucs.py`.

| Argument | Default | Description |
|----------|---------|-------------|
| `--input` | *(required)* | Path to flat input GPKG file |
| `--run-name` | *(required)* | Short name for this run |
| `--huc-column` | `huc8` | Column name to group bridges by |
| `--osmid-column` | `osmid` | Column name for bridge OSM IDs |
| `--gpkg-template` | `osm_bridges_lidar_subset__{huc_id}.gpkg` | Filename template |
| `--runs-dir` | `./data/runs` | Root directory for runs |
| `--force` | False | Overwrite existing run directory |

**Output structure:**

```
data/runs/{run-name}/
├── input/{original_filename}.gpkg
├── hucs/{huc_id}/osm_bridges_lidar_subset__{huc_id}.gpkg
├── source/
├── silver_training/
├── predictions/
└── run_config.json
```

---

### `utils/download_osm_hucs.py`

Downloads OSM bridge GeoPackages by HUC from S3.
Has two modes: **info** (omit `--dir`, lists HUC IDs and bridge counts) and **download** (provide `--dir`, saves per-HUC folders).

| Argument | Default | Description |
|----------|---------|-------------|
| `--profile` | None | AWS profile name |
| `--dir` | None | Local output directory (enables download mode) |
| `--bucket` | `noaa-nws-owp-fim` | S3 bucket name |
| `--prefix` | `hand_fim/hand_4_8_7_2/` | Base S3 prefix |
| `--all` | False | Download all HUCs (otherwise uses `--limit`) |
| `--limit` | 100 | Number of HUCs to process |
| `--workers` | `min(32, cpu_count+4)` | Worker processes |
| `--save-subsets` | `both` | Which filtered subsets: `lidar`, `not_lidar`, or `both` |

---

### `utils/download_bridge_lidar.py`

Downloads raw lidar point clouds for OSM bridges without applying weak supervision.
Lightweight alternative to `download_and_weak_supervise_hucs.py` for bridges that only need source LAZ.

| Argument | Default | Description |
|----------|---------|-------------|
| `--hucs-dir` | `./data/osm/hucs` | Directory containing per-HUC GPKG files |
| `--lidar-resources` | `./data/usgs_entwine/lidar_resources.geojson` | USGS EPT source index |
| `--output-dir` | `./data/ml-data/not_lidar_source` | Output directory |
| `--gpkg-pattern` | `osm_bridges_lidar_subset__*.gpkg` | Glob pattern for GPKG files |
| `--hucs` | all | Space-separated HUC IDs to process |
| `--osm-ids` | all | Space-separated OSM IDs to process |
| `--skip-existing` | False | Skip bridges already downloaded |
| `--workers` | CPU count | Parallel worker processes |

---

## Visualization

### `utils/visualize_pointcloud.py`

Renders side-by-side 3D LiDAR point cloud figures for poster/presentation use.

| Mode | Left panel | Right panel |
|------|-----------|-------------|
| `gold-vs-model` | Human annotations (gold NPY) | Model predictions (inference LAZ) |
| `source-vs-silver` | Raw elevation (source LAZ) | Weak supervision labels (silver LAZ) |

| Argument | Default | Description |
|----------|---------|-------------|
| `--gold` / `--source` | *(required)* | Left panel input file |
| `--model` / `--silver` | *(required)* | Right panel input file |
| `-o` / `--output` | `notebooks/outputs/gold_vs_model.png` | Output PNG file path |
| `--title` | None | Figure suptitle |
| `--elev` | 30 | 3D view elevation angle |
| `--azim` | 225 | 3D view azimuth angle |
| `--point-size` | 8 | Scatter point size |
| `--max-points` | 50000 | Downsample limit per cloud |
| `--dpi` | 300 | Output resolution |
| `--font-scale` | 1.0 | Multiply all font sizes (1.5-1.8 for posters) |
| `--border-width` | 0 | Border width in points (0 = no border) |

```bash
python utils/visualize_pointcloud.py gold-vs-model \
    --gold data/ml-data/gold-data-normalized/03070101/bridge_40787878.npy \
    --model data/ml-data/evaluation_results/v5-gold-134/inference_output/03070101/bridge_40787878.laz \
    -o notebooks/outputs/gold_vs_model.png
```

---

### `utils/visualize_metrics.py`

Plots training curves from PyTorch Lightning CSVLogger output.
Supports single experiment, multi-experiment comparison, and merging resumed runs.

| Argument | Default | Description |
|----------|---------|-------------|
| `--csv` | None | Direct path to `metrics.csv` |
| `--root` | `./experiments` | Experiments root directory |
| `--exp` | `bridge_classify_base` | Experiment name |
| `--ver` | 0 | Version number |
| `--compare` | None | Comma-separated experiment names to plot together |
| `--compare-versions` | None | Comma-separated versions for compare mode |
| `--merge-resumed` | False | Merge two experiments into one continuous timeline |
| `--out` | None | Output PNG file path |
| `--annotate-best` | None | Validation metric to annotate with best epoch |

---

## Verification & Sampling

### `utils/verify_lidar_subset.py`

Verifies that `osm_bridges_lidar_subset__{huc_id}.gpkg` matches the filtered rows of the full GeoPackage where `has_lidar_tif == 'Y'`.
Works with local data or S3. Randomly samples HUCs for spot-check.

| Argument | Default | Description |
|----------|---------|-------------|
| `--dir` | `./data/osm/hucs` | Local directory containing HUC subdirs |
| `--s3` | False | Sample and verify from S3 |
| `--profile` | None | AWS profile (for `--s3`) |
| `--bucket` | `fimc-data` | S3 bucket (for `--s3`) |
| `--prefix` | `bridge-classification/osm/hucs/` | S3 prefix (for `--s3`) |
| `--sample` | 10 | Number of HUCs to sample |

---

### `utils/extract_complex_bridges.py`

Extracts curved/arched bridge rejections from processing logs.
Parses logs for bridges rejected by the RANSAC linearity check, deduplicates, excludes bridges already in training data, and produces a stratified random sample.

| Argument | Default | Description |
|----------|---------|-------------|
| `--log-dirs` | `logs/server-logs/` | Directory(ies) containing log files |
| `--exclude-ids` | None | ID files to exclude (split files) |
| `--source-s3-uri` | None | S3 URI prefix for source files |
| `--profile` | None | AWS profile name |
| `--output` | `data/ml-data/complex_bridges_all.csv` | Output CSV |
| `--sample-output` | `data/ml-data/complex_bridges_sample_100.csv` | Stratified sample CSV |
| `--sample-size` | 100 | Number of bridges to sample |
| `--max-per-huc` | 3 | Maximum bridges per HUC |
| `--seed` | 27 | Random seed |

---

### `utils/find_new_source_candidates.py`

Finds bridge+lidar source combinations not in existing train/val/test splits for gold annotation campaigns.
Scans per-HUC GPKGs, queries lidar sources spatially, diffs against split files, outputs stratified sample.

| Argument | Default | Description |
|----------|---------|-------------|
| `--proven-linear` | None | `true` = same bridge new source; `false` = unseen bridges; omit = both |
| `--sample-size` | 50 | Number of candidates to sample (0 = all) |
| `--max-per-huc` | 3 | Maximum candidates per HUC |
| `--lidar-resources` | *(required)* | USGS EPT source index |
| `--hucs-dir` | *(required)* | Directory containing per-HUC GPKG files |
| `--split-dir` | *(required)* | Directory containing split ID files |
| `--output-dir` | *(required)* | Output directory for CSV + helper files |
| `--no-progress` | False | Disable progress bar |

**Outputs:** CSV files with candidate bridge+source pairs, plus `sample_hucs.txt` and `sample_osm_ids.txt`.

---

### `utils/verify_ransac_parity.py`

Verifies RANSAC determinism across platforms using synthetic bridge data.
No CLI arguments. Run directly: `python utils/verify_ransac_parity.py`
