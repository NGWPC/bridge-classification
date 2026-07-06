# API Reference

Auto-generated from source docstrings.
For narrative documentation, see [Architecture](../architecture.md) and [Data Pipeline](../data-pipeline.md).

| Section | Modules | Description |
|---------|---------|-------------|
| [Core & Constants](core.md) | `constants`, `logging_utils` | Shared enums, constants, timeout guard, logging setup |
| [Data I/O & Processing](data-io.md) | `las_io`, `voxelization`, `lidar_utils`, `gpkg_utils` | LAS/GeoPackage I/O, voxelization, spatial utilities |
| [Weak Supervision](weak-supervision.md) | `weak_supervision`, `preprocess_bridges`, `download_and_weak_supervise_hucs`, `download_and_weak_supervise_demo` | RANSAC labeling algorithm and data generation pipeline |
| [Model & Training](model-training.md) | `model`, `dataset`, `train` | Sparse 3D U-Net, dataset loader, PyTorch Lightning training |
| [Inference & Cloud](inference-cloud.md) | `inference`, `s3_client`, `s3_paths`, `s3_audit`, `model_registry` | Production inference and S3 operations |
| [Utility Scripts](utils.md) | `evaluate_model`, `compare_experiments`, `register_model`, `promote_model`, `split_data`, `calculate_weights`, `visualize_pointcloud`, `visualize_metrics`, and more | Evaluation, data preparation, visualization, verification |
