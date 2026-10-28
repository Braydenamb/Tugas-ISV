"""Additional processing locates image measurements, never ideal model points."""
import cv2 as cv
import numpy as np

CRITERIA = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 60, 0.001)
PROFILES = ("baseline", "mild")


def prepare(gray, profile):
    if profile == "baseline":
        return gray, gray
    if profile != "mild":
        raise ValueError(f"Profil tidak dikenal: {profile}")
    # CLAHE is used to locate features; final refinement avoids its altered contrast.
    clean = cv.GaussianBlur(gray, (3, 3), 0.8)
    detection = cv.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(clean)
    return detection, clean


def automatic_seed(gray, pattern):
    """Fallback for new images with no matching, verified dataset seed."""
    scale = min(1.0, 1040 / max(gray.shape))
    small = cv.resize(gray, None, fx=scale, fy=scale, interpolation=cv.INTER_AREA)
    for blur in (0, 3, 5, 7, 9, 13, 17):
        image = small if blur == 0 else cv.GaussianBlur(small, (blur, blur), 0)
        ok, corners = cv.findChessboardCorners(
            image, pattern, cv.CALIB_CB_ADAPTIVE_THRESH | cv.CALIB_CB_NORMALIZE_IMAGE
        )
        if not ok:
            ok, corners = cv.findChessboardCornersSB(image, pattern, cv.CALIB_CB_NORMALIZE_IMAGE)
        if ok:
            points = corners.reshape(-1, 1, 2).astype(np.float32)
            points[:, :, 0] *= gray.shape[1] / small.shape[1]
            points[:, :, 1] *= gray.shape[0] / small.shape[0]
            return points
    raise ValueError("Pola lengkap tidak ditemukan; perlu foto/penandaan awal yang lebih jelas")


def remeasure(gray, initial, pattern, profile):
    """Use a homography only to define search windows, then measure actual pixels."""
    cols, rows = pattern
    grid = np.mgrid[:cols, :rows].T.reshape(-1, 2).astype(np.float32)
    if initial.shape != (cols * rows, 1, 2) or not np.isfinite(initial).all():
        raise ValueError("Koordinat awal tidak sesuai pola atau bukan angka finite")
    H, inliers = cv.findHomography(
        grid, initial.reshape(-1, 2), cv.RANSAC, 8.0, maxIters=5000, confidence=0.999
    )
    if H is None:
        raise ValueError("Inisialisasi homografi gagal")
    W = np.array([[100.0, 0, 200], [0, 100.0, 200], [0, 0, 1.0]])
    M = W @ np.linalg.inv(H)
    detection, refinement = prepare(gray, profile)
    dimensions = ((cols + 3) * 100, (rows + 3) * 100)
    warp = cv.warpPerspective(detection, M, dimensions)
    # Refinement uses non-CLAHE intensities in both coordinate systems.
    refine_warp = cv.warpPerspective(refinement, M, dimensions) if profile != "baseline" else warp
    smooth = cv.GaussianBlur(warp, (7, 7), 1.5)
    response = cv.cornerMinEigenVal(smooth, 7, 3)
    measured, evidence = [], []
    radius = 24
    yy, xx = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    weighting = np.exp(-(xx ** 2 + yy ** 2) / (2 * 18 ** 2))
    for index, (gx, gy) in enumerate(grid):
        x0, y0 = int(200 + 100 * gx), int(200 + 100 * gy)
        roi = response[y0-radius:y0+radius+1, x0-radius:x0+radius+1]
        iy, ix = np.unravel_index(np.argmax(roi * weighting), roi.shape)
        if ix in (0, 2 * radius) or iy in (0, 2 * radius) or roi[iy, ix] <= 0:
            raise ValueError(f"Sudut {index}: respons lemah/di batas pencarian; perlu audit")
        measured.append([x0 - radius + ix, y0 - radius + iy])
        evidence.append([float(roi[iy, ix]), int(ix-radius), int(iy-radius)])
    peaks = np.float32(measured).reshape(-1, 1, 2)
    subpixel = cv.cornerSubPix(refine_warp, peaks.copy(), (5, 5), (-1, -1), CRITERIA)
    if np.max(np.linalg.norm(subpixel - peaks, axis=2)) > 8:
        raise ValueError("Refinement bergeser >8 piksel pada citra perataan; perlu audit")
    points = cv.perspectiveTransform(subpixel, np.linalg.inv(M)).astype(np.float32)
    refined = cv.cornerSubPix(refinement, points.copy(), (5, 5), (-1, -1), CRITERIA)
    movement = np.linalg.norm((refined - points).reshape(-1, 2), axis=1)
    accepted = movement <= 4
    points[accepted] = refined[accepted]
    height, width = gray.shape
    if not np.isfinite(points).all() or np.any(points[:, 0, 0] < 0) or np.any(points[:, 0, 0] >= width) or np.any(points[:, 0, 1] < 0) or np.any(points[:, 0, 1] >= height):
        raise ValueError("Titik hasil pengukuran berada di luar foto")
    return points, {
        "profile": profile,
        "homography_inliers_for_initialization_only": int(inliers.sum()),
        "local_corner_response_offsets": evidence,
        "final_refinement_movement_px": movement.tolist(),
        "final_refinement_applied": accepted.tolist(),
        "coordinate_system": "original image pixels",
    }
