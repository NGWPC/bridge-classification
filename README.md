# USGS Lidar Bridge Classification

A comprehensive pipeline for processing bridge lidar data organized by Hydrologic Unit Code (HUC) regions. This project downloads lidar point cloud data, applies weak supervision rules for labeling, normalizes coordinates, and prepares data for machine learning model training.

## Project Overview

This project provides tools for:

- **Data Download & Weak Supervision**: Downloads lidar data from USGS Entwine sources and applies automated labeling rules to identify bridge decks, ground, water, and obstacles
- **Data Normalization**: Normalizes point cloud coordinates and remaps classification labels for model training
- **Model Training**: Prepares normalized data for training sparse 3D U-Net models for bridge point cloud classification

The pipeline processes bridge geometries from OpenStreetMap, finds intersecting lidar sources, applies ground filtering (SMRF), performs quality checks (RANSAC plane fitting, linearity validation), and generates labeled training data.

## Installation

### Prerequisites

- Python 3.11
- Conda or Mamba package manager

### Setup

```bash
# Create mamba/ conda environment
mamba create -n bridge-classify python=3.11
mamba activate bridge-classify

# Install core dependencies
mamba install -c conda-forge python-pdal gdal entwine matplotlib geopandas tqdm seaborn
# if needed interactive shell
mamba install ipython

# Install additional ML dependencies (if needed for training)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126 # adjust cuda version as needed
pip install lightning
pip install tensorboard

# for saving graph
# pip install torchview graphviz
# on linux, you also need an OS-level graphviz package
# sudo apt-get install graphviz

# pip install spconv # for CPU (only for forward pass and network check)
# needs gpu for full training
pip install spconv-cu120 # Adjust CUDA version as needed (https://github.com/traveller59/spconv)
# Note: you need version 1 of numpy for spconv to
# avoid the Floating point exception (core dumped) error
# More info here: https://github.com/traveller59/spconv/issues/725
mamba install numpy=1.26.4


# later when running script if getting an error
# Error: /lib/x86_64-linux-gnu/libstdc++.so.6: version `CXXABI_1.3.15' not found
#mamba install -c conda-forge libstdcxx-ng
# if above doesn't work; run this in terminal before starting the script
# export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
```

### Data Download
- Make a folder named `data/` in the same level as `src/`
- Make a subfolder `usgs_entwine/` and `osm/hucs/` inside `data/` folder.
- Download the usgs lidar resources as `wget https://raw.githubusercontent.com/hobuinc/usgs-lidar/refs/heads/master/boundaries/resources.geojson -O data/usgs-entwine/lidar_resources.geojson`
- HUCS level osm data can be found at `s3://fimc-data/bridge-classification/osm/hucs/` (organized by huc_id folder level)

### Additional Dependencies

For model training (needs GPU machine):
- PyTorch
- PyTorch Lightning
- spconv (sparse convolution library)

## Classification Labels for Training

The pipeline uses the following classification scheme:

- **0**: Background/Unclassified
- **1**: Ground (from SMRF ground filtering)
- **2**: Water
- **3**: Bridge Deck (target class)
- **4**: Obstacles/High Noise (cars, poles, etc.)

## Output Structure

### File Naming Conventions

**Download & Weak Supervision**:
- Source files: `bridge_{osmid}_{source_name}.laz`
- Silver files: `bridge_{osmid}_{source_name}.laz`

**Normalization**:
- Data files: `bridge_{osmid}_{source_name}.npy`
- Metadata files: `bridge_{osmid}_{source_name}.json`

### Metadata JSON Structure

The normalization script generates JSON metadata files with the following structure:

```json
{
    "original_file": "bridge_123456_source.laz",
    "original_path": "/path/to/original/file.laz",
    "offsets": {
        "x_center": 1234567.89,
        "y_center": 9876543.21,
        "z_min": 45.67
    },
    "stats": {
        "point_count": 100000,
        "bridge_points": 5000,
        "ground_points": 80000,
        "water_points": 0,
        "noise_points": 2000,
        "background_points": 13000
    },
    "class_distribution": {
        "0": 13000,
        "1": 80000,
        "2": 0,
        "3": 5000,
        "4": 2000
    }
}
```
