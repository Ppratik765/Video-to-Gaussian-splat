import cv2
import numpy as np


def compute_blur(image: np.ndarray) -> float:
    """
    Variance of Laplacian.
    Expects grayscale image.
    """
    return float(cv2.Laplacian(image, cv2.CV_64F).var())

def compute_exposure_flicker(luminance_sequence: list[float]) -> float:
    """
    Measure of exposure stability across frames.
    """
    if len(luminance_sequence) < 2:
        return 0.0
    arr = np.array(luminance_sequence)
    diffs = np.abs(np.diff(arr))
    return float(np.mean(diffs))

def compute_flow_parallax(
    flows_and_rig_views: list[tuple[np.ndarray, float, float, float, np.ndarray]]
) -> tuple[float, float, float]:
    """
    Given a list of (flow_field, focal_length, cx, cy, R_c2w) for each camera view,
    fit a global angular velocity to the optical flows using least squares.
    Subtract the rotational flow to obtain the residual (translational) flow.
    Returns: (median_residual_parallax, median_rotational_flow, rotation_ratio)
    """
    A_list = []
    b_list = []

    # Subsample factor to speed up the least squares fit
    step = 16

    for flow, f, cx, cy, R_c2w in flows_and_rig_views:
        h, w = flow.shape[:2]
        # Create grid
        y, x = np.mgrid[0:h:step, 0:w:step]
        y_flat = y.flatten()
        x_flat = x.flatten()

        # Normalized coordinates
        xp = (x_flat - cx) / f
        yp = (y_flat - cy) / f

        # Jacobian for pinhole camera: J * w_c = (du, dv)^T
        # du = f * (-xp*yp * w_x + (1 + xp^2) * w_y - yp * w_z)
        # dv = f * (-(1 + yp^2) * w_x + xp*yp * w_y + xp * w_z)
        J_u = f * np.stack([-xp*yp, 1 + xp**2, -yp], axis=-1)
        J_v = f * np.stack([-(1 + yp**2), xp*yp, xp], axis=-1)

        # J_c maps camera angular velocity to flow.
        # w_c = R_w2c * w_world = R_c2w.T * w_world
        # So J_world = J_c @ R_c2w.T
        R_w2c = R_c2w.T

        J_u_world = J_u @ R_w2c
        J_v_world = J_v @ R_w2c

        # We interleave u and v rows
        N = xp.shape[0]
        A_cam = np.zeros((2*N, 3), dtype=np.float32)
        A_cam[0::2] = J_u_world
        A_cam[1::2] = J_v_world

        flow_u = flow[y_flat, x_flat, 0]
        flow_v = flow[y_flat, x_flat, 1]
        b_cam = np.zeros((2*N,), dtype=np.float32)
        b_cam[0::2] = flow_u
        b_cam[1::2] = flow_v

        A_list.append(A_cam)
        b_list.append(b_cam)

    A = np.concatenate(A_list, axis=0)
    b = np.concatenate(b_list, axis=0)

    # Solve for w_world (3,)
    # using lstsq
    w_world, _, _, _ = np.linalg.lstsq(A, b, rcond=None)

    # Now compute median rotational and residual over the WHOLE flow field (or at least the subsampled grid)
    # Actually, computing it over the subsampled grid is fine and fast.
    b_rot = A @ w_world
    b_res = b - b_rot

    # Reshape back to (N_total, 2)
    b_rot_2d = b_rot.reshape(-1, 2)
    b_res_2d = b_res.reshape(-1, 2)

    mag_rot = np.linalg.norm(b_rot_2d, axis=-1)
    mag_res = np.linalg.norm(b_res_2d, axis=-1)

    median_rot = float(np.median(mag_rot))
    median_res = float(np.median(mag_res))

    rot_ratio = 0.0
    if (median_rot + median_res) > 1e-6:
        rot_ratio = median_rot / (median_rot + median_res)

    return median_res, median_rot, rot_ratio
