# Core & Constants

Shared constants, enums, and lightweight utilities that form the foundation of the pipeline.
These modules have no heavy dependencies (no torch, spconv, pdal, numpy) and can be imported anywhere.

!!! tip "See also"
    [Architecture: Classification Schema](../architecture.md#classification-schema) for the 4-class schema defined in `constants.py`

---

### Constants

| Constant | Value / Type | Description |
| --- | --- | --- |
| `NUM_CLASSES` | `4` | Number of model output classes |
| `CLASS_NAMES` | dict | `{0: "Background", 1: "Ground/Water", 2: "Bridge Deck", 3: "Obstacles"}` |
| `CLASS_COLORS` | dict | Matplotlib colors per class (`black`, `orange`, `blue`, `yellow`) |
| `CLASS_COLORS_HEX` | dict | High-contrast hex palette for publication figures |
| `BRIDGE_DECK_MODEL_CLASS` | `2` | Model class for bridge deck |
| `BRIDGE_DECK_ASPRS_CODE` | `17` | ASPRS code for bridge deck |
| `OBSTACLES_MODEL_CLASS` | `3` | Model class for obstacles |
| `OBSTACLES_ASPRS_CODE` | `18` | ASPRS code for obstacles |
| `VOXEL_SIZE` | `0.1` | Default voxel size in meters |
| `SPATIAL_SHAPE_PADDING` | `10` | Padding added to voxel grid spatial shape |
| `MIN_POINT_COUNT` | `100` | Skip files with fewer points |
| `BRIDGE_TIMEOUT` | `150` | Default per-bridge timeout in seconds |
| `AWS_MAX_RETRIES` | `3` | Max S3 retry attempts (adaptive mode) |

### Class Mapping (ASPRS to Model)

Used at preprocessing/training time (`LAS_TO_MODEL_MAP`):

| ASPRS Code | ASPRS Name | Model Class | Model Name |
| --- | --- | --- | --- |
| 2 | Ground | 1 | Ground/Water |
| 9 | Water | 1 | Ground/Water |
| 17 | Bridge Deck | 2 | Bridge Deck |
| 18 | High Noise | 3 | Obstacles |
| all others | - | 0 | Background |

Used at inference time (`MODEL_TO_LAS_MAP`):

| Model Class | Model Name | ASPRS Code | ASPRS Name |
| --- | --- | --- | --- |
| 0 | Background | 1 | Unclassified |
| 1 | Ground/Water | 2 | Ground |
| 2 | Bridge Deck | 17 | Bridge Deck |
| 3 | Obstacles | 18 | High Noise |

::: src.constants

---

::: src.logging_utils
