# Bridge Classification

USGS LiDAR Bridge Point Cloud Classification Pipeline

---

## Overview

An end-to-end pipeline for classifying 3D LiDAR point clouds around bridges from
USGS 3DEP data into 4 semantic classes using a sparse 3D U-Net. The pipeline covers
data acquisition through inference, with automated weak supervision for scalable
training data generation (550K+ bridges).

See [Architecture](architecture.md) for the classification schema and system design.

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | System design, classification schema, full algorithm details |
| [Data Pipeline](data-pipeline.md) | Step-by-step data flow with shapes at each stage |
| [AWS Batch Inference](aws-batch-inference.md) | Scaling inference with AWS Batch array jobs |
| [Module Reference](module-reference.md) | Every module's public API and CLI arguments |
| [Design Decisions](decisions.md) | Rationale for key architectural choices |

## Getting Started

See the [README](https://github.com/NGWPC/bridge-classification#readme) for full installation and pipeline run commands.
