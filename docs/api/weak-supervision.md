# Weak Supervision Pipeline

Deterministic weak labeling algorithm for generating silver training data from raw LiDAR.
Implements Phases A (download & weak supervise) and B (preprocess) of the pipeline.

!!! tip "See also"
    - [Architecture: Phase A](../architecture.md#phase-a-silver-data-generation-weak-supervision) for the RANSAC plane fitting algorithm design
    - [Data Pipeline: Step 1](../data-pipeline.md#step-1-download-weak-supervise) for the step-by-step data flow

---

::: src.weak_supervision

---

::: src.preprocess_bridges

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--input-dir` | `./data/ml-data/silver_training` | Input directory with HUC-organized LAZ/LAS files |
| `--output-dir` | `./data/ml-data/silver_training_normalized` | Output directory for `.npy` and `.json` |
| `--skip-existing` | False | Skip if `.npy` + `.json` already exist |
| `--hucs` | all | Specific HUC IDs to process |
| `--workers` | CPU count | Parallel workers per HUC |
| `--no-progress` | False | Disable progress bars |

### Usage

```bash
# Process all HUCs
python src/preprocess_bridges.py

# Process specific HUCs with resume
python src/preprocess_bridges.py --hucs 02050206 03070101 --skip-existing
```

---

::: src.download_and_weak_supervise_hucs

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--hucs-dir` | `./data/osm/hucs` | Directory containing per-HUC GPKG files |
| `--source-dir` | `./data/ml-data/source` | Output directory for raw LAZ downloads |
| `--silver-dir` | `./data/ml-data/silver_training` | Output directory for weak-supervised LAZ |
| `--lidar-resources` | `./data/usgs_entwine/lidar_resources.geojson` | USGS EPT source index |
| `--hucs` | all | Space-separated HUC IDs to process |
| `--osm-ids` | all | Space-separated OSM IDs to process |
| `--buffer` | 10.0 | Bridge geometry buffer in meters |
| `--workers` | CPU count | Parallel worker processes |
| `--skip-existing` | False | Skip bridges already processed |
| `--bridge-timeout` | 300 | Seconds before a hung bridge is skipped |
| `--shuffle-seed` | None | Seed for task shuffle (reproducible order for debugging) |
| `--results-csv` | None | Write per-bridge results to this CSV path |
| `--log-dir` | `./logs` | Directory for processing logs |
| `--no-progress` | False | Disable tqdm progress bars |

### Usage

```bash
# Process all HUCs
python src/download_and_weak_supervise_hucs.py

# Process specific HUCs with resume
python src/download_and_weak_supervise_hucs.py \
    --hucs 02050206 03070101 \
    --skip-existing

# Custom output paths and timeout
python src/download_and_weak_supervise_hucs.py \
    --source-dir /data/source \
    --silver-dir /data/silver \
    --bridge-timeout 600 \
    --results-csv results.csv
```

---

::: src.download_and_weak_supervise_demo
