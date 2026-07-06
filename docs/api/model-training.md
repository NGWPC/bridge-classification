# Model & Training

Sparse 3D U-Net architecture, bridge point cloud dataset, and PyTorch Lightning training loop.
Implements Phases D (model) and E (training) of the pipeline.

!!! tip "See also"
    - [Architecture: Phase D](../architecture.md#phase-d-model-architecture) for the encoder-decoder design
    - [Architecture: Phase E](../architecture.md#phase-e-training) for training configuration

---

::: src.model

---

::: src.dataset

---

::: src.train

### train.py CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--data-dir` | `./data/ml-data` | Data directory for test loader and visualize when not using --train-dir |
| `--train-dir` | `./data/ml-data/training` | Training data directory |
| `--val-dir` | None | Validation directory; if unset, uses `--val-split` |
| `--val-split` | 0.0 | Fraction of training data to use as validation (0 = none) |
| `--voxel-size` | 0.1 | Voxel size in meters |
| `--max-voxels` | None | Max voxels per sample; subsampled if exceeded (OOM prevention) |
| `--batch-size` | 16 | Batch size |
| `--augment` | False | Enable random Z-rotation + jitter |
| `--augment-extra` | False | Extra augmentation: XY-flip, scaling, intensity jitter, point dropout. Requires `--augment` |
| `--dice-loss` | False | Use combined Dice + CrossEntropy loss (0.5*CE + 0.5*Dice) |
| `--train` | False | Enable training mode |
| `--epochs` | 50 | Training epochs |
| `--learning-rate` | 0.001 | AdamW learning rate |
| `--weight-decay` | 0.01 | AdamW weight decay |
| `--base-channels` | 16 | U-Net base channel count |
| `--num-workers` | 4 | DataLoader workers |
| `--exp-name` | `bridge_classify_base` | Experiment name for logs/checkpoints |
| `--experiments-dir` | `./experiments` | Base directory for experiments |
| `--class-weights` | None | Path to `class_weights.json` from `calculate_weights.py` |
| `--gpus` | auto | Number of GPUs (None = auto-detect). GPU required. |
| `--early-stopping` | False | Stop when monitored metric stops improving |
| `--early-stopping-patience` | 10 | Epochs to wait before early stopping |
| `--monitor` | `val_deck_iou` | Metric for checkpointing + early stopping |
| `--accumulate-grad-batches` | 1 | Gradient accumulation steps |
| `--ckpt-path` | None | Checkpoint path to resume training from |
| `--finetune` | None | Checkpoint for fine-tuning (weights only, fresh optimizer/epoch). Mutually exclusive with `--ckpt-path` |
| `--freeze-encoder` | False | Freeze encoder; only decoder and classifier are trained |
| `--save-top-k` | 5 | Number of best checkpoints to keep |
| `--visualize` | False | Visualize voxelization for a sample |
| `--sample-idx` | 0 | Sample index to visualize |

### train.py Usage Examples

```bash
# Basic training
python src/train.py --train \
    --train-dir ./data/ml-data/training \
    --val-dir ./data/ml-data/validation \
    --class-weights ./data/ml-data/class_weights.json \
    --exp-name my-experiment \
    --epochs 50 --batch-size 16 --augment

# Resume from checkpoint
python src/train.py --train \
    --train-dir ./data/ml-data/training \
    --val-dir ./data/ml-data/validation \
    --class-weights ./data/ml-data/class_weights.json \
    --ckpt-path ./experiments/my-experiment/version_0/checkpoints/last.ckpt \
    --exp-name my-experiment-resumed

# Fine-tune from a pretrained model (fresh optimizer, new experiment)
python src/train.py --train \
    --train-dir ./data/ml-data/gold-data-normalized \
    --val-dir ./data/ml-data/gold-data-normalized-val \
    --finetune ./experiments/base-model/version_0/checkpoints/best.ckpt \
    --exp-name fine-tuned-gold \
    --epochs 30 --learning-rate 0.0005 --freeze-encoder
```
