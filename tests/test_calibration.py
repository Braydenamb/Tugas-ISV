"""Focused checks for coordinate mapping and the two distinct error definitions."""
from pathlib import Path
import csv
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2 as cv
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from isv_calibration.calibration import calibrate, error_metrics, load_config
from isv_calibration.preprocessing import remeasure
from isv_calibration.alternatives import correlation_corners


def synthetic_checkerboard():
    canvas = np.full((840, 840), 150, np.uint8)
    yy, xx = np.indices((640, 640))
    canvas[100:740, 100:740] = np.where((xx // 80 + yy // 80) % 2, 235, 20)
    source = np.float32([[0, 0], [839, 0], [839, 839], [0, 839]])
    target = np.float32([[140, 65], [1120, 140], [1030, 885], [65, 760]])
    H = cv.getPerspectiveTransform(source, target)
    image = cv.warpPerspective(canvas, H, (1280, 960))
    grid = np.mgrid[:7, :7].T.reshape(-1, 2).astype(np.float32)
    truth = cv.perspectiveTransform((179.5 + grid * 80).reshape(-1, 1, 2), H)
    initial = truth + np.random.default_rng(42).normal(0, 1, truth.shape).astype(np.float32)
    return image, truth, initial


class MeasurementTests(unittest.TestCase):
    def test_replaced_photo_does_not_reuse_cached_coordinates(self):
        # A known filename with different pixels must be detected again, not filled
        # from historical corners. Failure must stop an insufficient-photo run.
        with tempfile.TemporaryDirectory(prefix="isv-changed-photo-") as folder:
            temporary = Path(folder)
            for name in ("data/photos", "config"):
                (temporary / name).mkdir(parents=True)
            for name in ("initial_corners.npz", "dataset_manifest.json"):
                shutil.copy2(ROOT / "data" / name, temporary / "data" / name)
            shutil.copy2(ROOT / "config/excluded_points.json", temporary / "config/excluded_points.json")
            for number in ("0046", "0074", "0091"):
                name = f"IMG-20261026-WA{number}.jpg"
                shutil.copy2(ROOT / "data/photos" / name, temporary / "data/photos" / name)
            changed = temporary / "data/photos/IMG-20261026-WA0046.jpg"
            self.assertTrue(cv.imwrite(str(changed), np.zeros((4160, 3120, 3), np.uint8)))
            config = load_config(ROOT / "config/calibration.json")
            config["minimum_photos"] = 3
            with patch("isv_calibration.calibration.ROOT", temporary), patch(
                "isv_calibration.calibration.automatic_seed", side_effect=ValueError("no image corner")
            ) as detector:
                with self.assertRaisesRegex(ValueError, "Hanya 2 foto"):
                    calibrate(config, temporary / "data/photos", temporary / "output", "baseline")
                detector.assert_called_once()
            with (temporary / "output/detection.csv").open() as handle:
                records = {row["file"]: row for row in csv.DictReader(handle)}
            self.assertEqual(records[changed.name]["status"], "detection_failed")

    def test_mean_distance_is_not_rms(self):
        observed = np.float32([[[0, 0]], [[0, 0]]])
        projected = np.float32([[[3, 4]], [[0, 0]]])
        distances, _ = error_metrics(observed, projected)
        self.assertAlmostEqual(float(distances.mean()), 2.5)
        self.assertAlmostEqual(float(np.sqrt(np.mean(distances ** 2))), np.sqrt(12.5), places=5)

    def test_both_profiles_return_original_perspective_coordinates(self):
        # Independent known geometry, not projected points from the fitted calibration.
        image, truth, initial = synthetic_checkerboard()
        for profile in ("baseline", "mild"):
            with self.subTest(profile=profile):
                points, _ = remeasure(image, initial.copy(), (7, 7), profile)
                error = np.linalg.norm((points - truth).reshape(-1, 2), axis=1)
                self.assertLess(float(error.mean()), 0.8)
                self.assertLess(float(error.max()), 1.5)

    def test_correlation_returns_observed_corner_not_noisy_initialization(self):
        image, truth, initial = synthetic_checkerboard()
        valid = np.mgrid[:7, :7].T.reshape(-1, 2)[:, 0] != 3
        points, diagnostics = correlation_corners(image, initial.copy(), valid)
        error = np.linalg.norm((points[valid] - truth[valid]).reshape(-1, 2), axis=1)
        self.assertEqual(len(diagnostics), 42)
        self.assertLess(float(error.mean()), 0.8)
        self.assertLess(float(error.max()), 1.5)


if __name__ == "__main__":
    unittest.main()
