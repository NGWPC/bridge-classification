"""Verify RANSAC reproducibility across platforms.

Generates a synthetic bridge plane with noise and outliers, runs RANSAC,
and prints coefficients + inlier count. Used to confirm deterministic
ordering produces identical results on Mac vs Linux (Ubuntu EC2).
"""

import numpy as np
from sklearn.linear_model import RANSACRegressor
import sys
import platform

def generate_synthetic_bridge(seed=42, n_points=1000):
    """
    Generates a synthetic 'bridge' (flat plane) with some noise
    and outliers to mimic the lidar data for testing RANSAC.
    """
    rng = np.random.default_rng(seed)

    # 1. Create a clean plane: Z = 0.05*X + 0.02*Y + 10
    X = rng.uniform(0, 100, n_points)
    Y = rng.uniform(0, 10, n_points)

    # Perfect plane
    Z = 0.05 * X + 0.02 * Y + 10

    # 2. Add sensor noise (Gaussian)
    Z += rng.normal(0, 0.05, n_points)

    # 3. Add Gross Outliers (simulating water/birds/noise)
    # Replaces 30% of data with random noise
    n_outliers = int(0.3 * n_points)
    outlier_indices = rng.choice(n_points, n_outliers, replace=False)
    Z[outlier_indices] += rng.uniform(-5, 5, n_outliers)

    return np.stack([X, Y], axis=1), Z

def run_test():
    print(f"--- Environment Info ---")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Machine: {platform.machine()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Numpy: {np.__version__}")
    print("-" * 30)

    # 1. Generate Data (Deterministic Seed)
    XY, Z = generate_synthetic_bridge(seed=42)

    # 2. Run RANSAC
    # Using the same random_state=27 from the config for reproducibility
    ransac = RANSACRegressor(
        min_samples=10,
        residual_threshold=0.20,
        random_state=27
    )

    print("\nFitting RANSAC...")
    ransac.fit(XY, Z)

    # 3. Extract Coefficients
    # The plane equation is: Z = (coef_x * X) + (coef_y * Y) + intercept
    coef_x, coef_y = ransac.estimator_.coef_
    intercept = ransac.estimator_.intercept_

    # 4. Count Inliers
    n_inliers = np.sum(ransac.inlier_mask_)

    print(f"\n--- RESULTS ---")
    print(f"Slope X (Coefficient): {coef_x:.15f}")
    print(f"Slope Y (Coefficient): {coef_y:.15f}")
    print(f"Intercept            : {intercept:.15f}")
    print(f"Number of Inliers    : {n_inliers}")

    return coef_x, coef_y, intercept

if __name__ == "__main__":
    run_test()

# OUTPUT:
# --------------------------
# --------- LINUX ----------
# --------------------------
# --- Environment Info ---
# OS: Linux 6.8.0-1044-aws
# Machine: x86_64
# Python: 3.11.14
# Numpy: 2.4.1
# ------------------------------

# Fitting RANSAC...

# --- RESULTS ---
# Slope X (Coefficient): 0.050122369905624
# Slope Y (Coefficient): 0.020419182797376
# Intercept            : 9.996581591759135
# Number of Inliers    : 722

# --------------------------
# --------- MACOS ----------
# --------------------------
# --- Environment Info ---
# OS: Darwin 25.2.0
# Machine: arm64
# Python: 3.11.14
# Numpy: 2.3.5
# ------------------------------

# Fitting RANSAC...

# --- RESULTS ---
# Slope X (Coefficient): 0.050122369905624
# Slope Y (Coefficient): 0.020419182797376
# Intercept            : 9.996581591759133
# Number of Inliers    : 722
