# Inference & Cloud

Production inference pipeline and S3 infrastructure.
Implements Phase F (inference) plus the cloud storage layer for model I/O, output auditing, and the model registry.

!!! tip "See also"
    - [Architecture: Phase F](../architecture.md#phase-f-inference) for the inference workflow
    - [AWS Batch Inference](../aws-batch-inference.md) for scaling with AWS Batch

---

::: src.inference

### CLI Arguments (`src/inference.py`)

| Argument | Default | Description |
|----------|---------|-------------|
| `--input` | None | Input LAS/LAZ file path (single-file mode) |
| `--output` | None | Output LAS/LAZ file path (single-file mode) |
| `--pairs-file` | None | TSV file with input/output pairs (batch mode) |
| `--model` | *(required)* | Path to `.ckpt` checkpoint |
| `--voxel-size` | 0.1 | Voxel size (must match training) |
| `--bridge-timeout` | 150 | Seconds before a hung bridge is skipped (batch mode) |
| `--mode` | `masked` | Output mode: `masked`, `raw`, or `both` |

**Modes:**

- `masked` - bridge deck only (class 2 to ASPRS 17) overlaid on original classification
- `raw` - all model classes replace original classification via `MODEL_TO_LAS_MAP`
- `both` - saves `_predicted` (raw) and `_bridge_masked` (masked) files

### Usage Examples

```bash
# Single file, masked mode (default)
python src/inference.py \
    --model ./experiments/my-model/checkpoints/epoch=35.ckpt \
    --input ./data/ml-data/testing/02050206/bridge_10598181.laz \
    --output ./data/ml-data/predictions/bridge_10598181_bridge_masked.laz

# Batch mode with pairs file (model loaded once, processes all pairs)
python src/inference.py \
    --pairs-file ./pairs.tsv \
    --model ./experiments/my-model/checkpoints/epoch=35.ckpt \
    --mode masked --bridge-timeout 150

# Both mode (saves _predicted and _bridge_masked side by side)
python src/inference.py \
    --model ./experiments/my-model/checkpoints/epoch=35.ckpt \
    --input ./bridge.laz --output ./bridge_predicted.laz \
    --mode both
```

---

::: src.s3_client

---

::: src.s3_paths

---

::: src.s3_audit

---

::: src.model_registry
