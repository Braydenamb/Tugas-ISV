"""Read actual photos, measure corners, and fit the lecture's planar camera model."""
from pathlib import Path
import csv
import hashlib
import json
import platform

import cv2 as cv
import numpy as np

from .preprocessing import automatic_seed, prepare, remeasure

ROOT = Path(__file__).resolve().parents[2]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    pattern = config.get("inner_corners")
    if not isinstance(pattern, list) or len(pattern) != 2 or any(type(x) is not int or x < 3 for x in pattern):
        raise ValueError("inner_corners harus dua bilangan bulat minimal 3")
    size = config.get("square_size_mm")
    if not isinstance(size, (int, float)) or not np.isfinite(size) or size <= 0:
        raise ValueError("square_size_mm harus positif dan finite")
    if type(config.get("minimum_photos")) is not int or config["minimum_photos"] < 3:
        raise ValueError("minimum_photos harus bilangan bulat minimal 3 (tugas ini: 12)")
    return config


def find_images(folder):
    if not folder.is_dir():
        raise ValueError(f"Folder foto tidak ditemukan: {folder}")
    images = sorted((p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_EXTENSIONS), key=lambda p: p.name)
    if not images:
        raise ValueError(f"Tidak ada foto di {folder}")
    if len({p.name for p in images}) != len(images):
        raise ValueError("Nama foto harus unik meskipun berada di subfolder berbeda")
    return images


def error_metrics(observed, projected):
    residuals = (observed - projected).reshape(-1, 2)
    distances = np.linalg.norm(residuals, axis=1)
    return distances, residuals


def _json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def calibrate(config, photos, output, profile):
    pattern = tuple(config["inner_corners"])
    cv.setNumThreads(config.get("threads", 4))
    cv.setRNGSeed(0)
    output.mkdir(parents=True, exist_ok=True)
    for name in ("corners", "audit", "preprocessing"):
        (output / name).mkdir(exist_ok=True)
    images = find_images(photos)
    count = pattern[0] * pattern[1]
    obj = np.zeros((count, 3), np.float32)
    obj[:, :2] = np.mgrid[:pattern[0], :pattern[1]].T.reshape(-1, 2) * config["square_size_mm"]
    manifest = _json(ROOT / config["dataset_manifest"]) or {}
    known_hashes = {row["file"]: row["sha256"] for row in manifest.get("images", [])}
    exclusions = _json(ROOT / config["excluded_points"]) or []
    seed_path = ROOT / config["initial_corners"]
    seeds = {}
    if seed_path.is_file() and manifest.get("inner_corners") == list(pattern):
        with np.load(seed_path, allow_pickle=False) as initial:
            seeds = {str(name): points.copy() for name, points in zip(initial["files"], initial["image_points"])}
    objects, observations, all_points, masks, accepted, records, used_exclusions = [], [], [], [], [], [], []
    image_size = None
    preview_written = False
    for path in images:
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        same_source = known_hashes.get(path.name) == sha and manifest.get("inner_corners") == list(pattern)
        row = {"file": path.name, "sha256": sha, "status": "", "reason": "", "seed_source": "", "points_used": 0}
        image = cv.imread(str(path))
        if image is None:
            row.update(status="unreadable", reason="Berkas tidak dapat dibaca sebagai gambar")
            records.append(row)
            continue
        gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
        dimensions = gray.shape[::-1]
        if image_size is None:
            image_size = dimensions
        if dimensions != image_size:
            row.update(status="different_resolution", reason=f"{dimensions} != {image_size}")
            records.append(row)
            continue
        try:
            if same_source and path.name in seeds:
                initial = seeds[path.name]
                row["seed_source"] = "verified_image_hash_and_saved_initialization"
            else:
                detection, _ = prepare(gray, profile)
                initial = automatic_seed(detection, pattern)
                row["seed_source"] = "automatic_image_detection"
            points, diagnostics = remeasure(gray, initial, pattern, profile)
        except (ValueError, cv.error, np.linalg.LinAlgError) as exc:
            row.update(status="detection_failed", reason=str(exc))
            records.append(row)
            print(f"  {path.name}: gagal deteksi ({exc})", flush=True)
            continue
        valid = np.ones(count, dtype=bool)
        if same_source:
            for entry in exclusions:
                if entry["file"] == path.name:
                    if not 0 <= entry["index"] < count:
                        raise ValueError(f"Indeks pengecualian tidak valid: {entry}")
                    valid[entry["index"]] = False
                    used_exclusions.append(entry)
        objects.append(obj[valid].copy())
        observations.append(points[valid].copy())
        all_points.append(points)
        masks.append(valid)
        accepted.append(path)
        (output / "audit" / f"{path.stem}.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
        display = image.copy()
        cv.drawChessboardCorners(display, pattern, points, True)
        for pt in points[~valid].reshape(-1, 2):
            cv.circle(display, tuple(np.round(pt).astype(int)), 25, (0, 165, 255), 5)
        height = int(780 * image.shape[0] / image.shape[1])
        cv.imwrite(str(output / "corners" / path.name), cv.resize(display, (780, height)))
        if not preview_written:
            detection, _ = prepare(gray, profile)
            a = cv.resize(gray, (390, int(390 * gray.shape[0] / gray.shape[1])))
            b = cv.resize(detection, (a.shape[1], a.shape[0]))
            cv.imwrite(str(output / "preprocessing" / "original_vs_detection.png"), np.hstack((a, b)))
            preview_written = True
        row.update(status="used", points_used=int(valid.sum()))
        records.append(row)
        print(f"  {path.name}: {int(valid.sum())} titik ({profile})", flush=True)
    with (output / "detection.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    if len(accepted) < config["minimum_photos"]:
        raise ValueError(f"Hanya {len(accepted)} foto lolos pengukuran; perlu {config['minimum_photos']}. Lihat detection.csv")
    rms, K, distortion, rotations, translations = cv.calibrateCamera(objects, observations, image_size, None, None)
    distances, residuals, per_photo = [], [], []
    for path, o, obs, rotation, translation in zip(accepted, objects, observations, rotations, translations):
        predicted, _ = cv.projectPoints(o, rotation, translation, K, distortion)
        errors, delta = error_metrics(obs, predicted)
        distances.extend(errors)
        residuals.extend(delta)
        per_photo.append({"file": path.name, "points_used": len(obs), "mean_error_px": float(errors.mean()), "rms_error_px": float(np.sqrt(np.mean(errors ** 2))), "max_error_px": float(errors.max())})
    distances = np.array(distances)
    recomputed_rms = float(np.sqrt(np.mean(distances ** 2)))
    if not np.isclose(rms, recomputed_rms, atol=1e-4):
        raise ValueError("RMS hasil perhitungan ulang berbeda dari keluaran OpenCV")
    result = {
        "profile": profile,
        "versions": {"opencv": cv.__version__, "numpy": np.__version__, "python": platform.python_version()},
        "images_total": len(images), "images_used": len(accepted), "observations_used": len(distances),
        "image_size": list(image_size), "inner_corners": list(pattern), "square_size_mm": config["square_size_mm"],
        "K": K.tolist(), "distortion_names": ["k1", "k2", "p1", "p2", "k3"], "distortion": distortion.ravel().tolist(),
        "mean_reprojection_error_px": float(distances.mean()), "rms_reprojection_error_px": float(rms),
        "rms_recomputed_px": recomputed_rms, "per_photo": per_photo, "excluded_points": used_exclusions,
        "inputs": records,
        "method_note": "Planar calibration following lecture; additional image-based corner measurement. No observations rejected using calibration residuals. Homography initializes search windows only. Final points use original image pixel coordinates.",
    }
    (output / "calibration.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    np.savez_compressed(output / "parameters.npz", K=K, distortion=distortion,
                        rvecs=np.array(rotations), tvecs=np.array(translations),
                        image_points=np.array(all_points), object_points=np.array([obj] * len(accepted)),
                        valid_mask=np.array(masks), image_size=np.array(image_size),
                        square_size_mm=np.array(config["square_size_mm"]), translation_unit=np.array("mm"),
                        files=np.array([p.name for p in accepted]))
    with (output / "errors_per_photo.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_photo[0]))
        writer.writeheader()
        writer.writerows(per_photo)
    from .reporting import write_outputs
    write_outputs(result, np.array(residuals), output)
    return result
