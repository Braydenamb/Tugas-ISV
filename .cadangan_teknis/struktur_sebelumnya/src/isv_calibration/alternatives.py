"""Experimental detector/model study; does not change the lecture baseline."""
from pathlib import Path
import csv
import hashlib
import json

import cv2 as cv
import numpy as np

from .calibration import ROOT, calibrate, error_metrics, find_images


def distortion_health(K, distortion, image_size):
    """Screen rational denominator poles; sensor-radius extent is approximate."""
    coefficients = np.zeros(8)
    flat = np.asarray(distortion).ravel()
    coefficients[:min(8, len(flat))] = flat[:8]
    roots = np.roots([coefficients[7], coefficients[6], coefficients[5], 1.0])
    poles = sorted(float(np.sqrt(x.real)) for x in roots if abs(x.imag) < 1e-6 and x.real > 0)
    width, height = image_size
    corners = np.array([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
    radius = float(np.linalg.norm((corners - K[:2, 2]) / np.diag(K)[:2], axis=1).max())
    xs = np.linspace(-K[0, 2]/K[0, 0], (width-1-K[0, 2])/K[0, 0], 31)
    ys = np.linspace(-K[1, 2]/K[1, 1], (height-1-K[1, 2])/K[1, 1], 31)
    xx, yy = np.meshgrid(xs, ys)
    points = np.column_stack([xx.ravel(), yy.ravel(), np.ones(xx.size)]).astype(np.float64)
    def project(p):
        image, _ = cv.projectPoints(p, np.zeros(3), np.zeros(3), np.eye(3), flat)
        return image.reshape(-1, 2)
    step = 1e-5
    dx = np.array([step, 0.0, 0.0])
    dy = np.array([0.0, step, 0.0])
    derivative_x = (project(points+dx)-project(points-dx))/(2*step)
    derivative_y = (project(points+dy)-project(points-dy))/(2*step)
    determinant = derivative_x[:, 0]*derivative_y[:, 1]-derivative_x[:, 1]*derivative_y[:, 0]
    finite = np.isfinite(determinant)
    return {"positive_radial_denominator_poles": poles,
            "approximate_sensor_corner_radius": radius,
            "pole_within_approximate_sensor_extent": any(pole < radius for pole in poles),
            "minimum_sampled_jacobian_determinant": float(determinant[finite].min()) if finite.any() else None,
            "nonpositive_or_nonfinite_jacobian_fraction": float(np.mean(~finite | (determinant <= 0))),
            "note": "Pole roots are exact. Radius/Jacobian use an approximate normalized sensor domain and a 31x31 sample grid; no poles or sampled folds does not prove invertibility or accuracy outside the observed target."}


def panel_masks(valid, axis):
    """Exclude the physical center seam uniformly, never using residuals."""
    grid = np.mgrid[:7, :7].T.reshape(-1, 2)
    if axis not in ("column", "row"):
        raise ValueError(f"Orientasi panel tidak valid: {axis}")
    coordinate = grid[:, 0 if axis == "column" else 1]
    return [valid & (coordinate < 3), valid & (coordinate > 3)]


def correlation_corners(gray, initial, valid, *, pixels_per_square=100, homography_valid=None):
    """Measure actual four-quadrant checker intensity using normalized correlation.

    No fitted camera projections are used. Pixel templates are evaluated on the
    photograph; a local quadratic interpolates the peak of their response.
    """
    if not isinstance(pixels_per_square, int) or pixels_per_square < 50:
        raise ValueError("Resolusi perataan harus bilangan bulat minimal 50 piksel/kotak")
    grid = np.mgrid[:7, :7].T.reshape(-1, 2).astype(np.float32)
    fit_mask = np.ones(49, dtype=bool) if homography_valid is None else np.asarray(homography_valid, dtype=bool)
    if fit_mask.shape != (49,) or fit_mask.sum() < 4:
        raise ValueError("Inisialisasi homografi memerlukan minimal empat titik")
    H, _ = cv.findHomography(grid[fit_mask], initial.reshape(-1, 2)[fit_mask], cv.RANSAC, 8.0)
    if H is None:
        raise ValueError("Homografi daerah pencarian korelasi gagal")
    scale = pixels_per_square
    W = np.float64([[scale, 0, 2*scale], [0, scale, 2*scale], [0, 0, 1]])
    mapping = W @ np.linalg.inv(H)
    warp = cv.warpPerspective(gray, mapping, (10*scale, 10*scale))
    template_size = 2 * round(0.16 * scale)
    radius = round(0.24 * scale)
    half_patch = radius + template_size // 2
    u = np.arange(template_size) - (template_size-1)/2
    xx, yy = np.meshgrid(u, u)
    template = np.sign(xx * yy).astype(np.float32)
    ys, xs = np.mgrid[-1:2, -1:2]
    design = np.column_stack([xs.ravel() ** 2, xs.ravel() * ys.ravel(), ys.ravel() ** 2,
                              xs.ravel(), ys.ravel(), np.ones(9)])
    measured, indices, diagnostics = [], [], []
    for index, (gx, gy) in enumerate(grid):
        if not valid[index]:
            continue
        x, y = int(2*scale + gx*scale), int(2*scale + gy*scale)
        patch = warp[y-half_patch:y+half_patch, x-half_patch:x+half_patch].astype(np.float32)
        score = np.abs(cv.matchTemplate(patch, template, cv.TM_CCOEFF_NORMED))
        iy, ix = np.unravel_index(np.argmax(score), score.shape)
        if ix in (0, 2*radius) or iy in (0, 2*radius):
            raise ValueError(f"Sudut {index}: puncak korelasi di batas, perlu audit")
        a, b, c, d, e, _ = np.linalg.lstsq(design, score[iy-1:iy+2, ix-1:ix+2].ravel(), rcond=None)[0]
        hessian = np.array([[2*a, b], [b, 2*c]])
        delta = np.linalg.solve(hessian, -np.array([d, e])) if np.linalg.det(hessian) > 1e-10 and a < 0 else np.zeros(2)
        if np.max(np.abs(delta)) > 1:
            delta[:] = 0
        measured.append([x-radius-0.5+ix+delta[0], y-radius-0.5+iy+delta[1]])
        indices.append(index)
        diagnostics.append({"point_index": int(index), "correlation": float(score[iy, ix]),
                            "subpixel_offset": delta.tolist(), "pixels_per_square": scale})
    result = initial.copy()
    if measured:
        result[indices] = cv.perspectiveTransform(np.float32(measured).reshape(-1, 1, 2), np.linalg.inv(mapping))
    if not np.isfinite(result).all():
        raise ValueError("Hasil korelasi bukan angka finite")
    return result, diagnostics


def _views(data, indices, model):
    views = []
    for index in indices:
        parts = panel_masks(data["valid_mask"][index], data["axes"][index])
        if model == "single_plane":
            parts = [parts[0] | parts[1]]
        for panel, mask in enumerate(parts):
            views.append({"photo": index, "panel": panel, "mask": mask,
                          "object": data["object_points"][index][mask].copy(),
                          "image": data["image_points"][index][mask].copy()})
    return views


def _fit(data, indices, model, flags=0):
    views = _views(data, indices, model)
    rms, K, D, rotations, translations = cv.calibrateCamera(
        [v["object"] for v in views], [v["image"] for v in views], tuple(data["image_size"]), None, None, flags=flags
    )
    return views, rms, K, D, rotations, translations


def _cross_validate(data, model, folds=5, flags=0):
    """Hold out photographs for K/D; held-out pose uses alternate anchors only."""
    all_indices = list(range(len(data["files"])))
    grid = np.mgrid[:7, :7].T.reshape(-1, 2)
    anchor_pattern = grid.sum(axis=1) % 2 == 0
    rows, plans = [], []
    for fold in range(folds):
        held_out = all_indices[fold::folds]
        training = [i for i in all_indices if i not in held_out]
        if set(training) & set(held_out):
            raise AssertionError("Training/validation image leakage")
        _, _, K, D, _, _ = _fit(data, training, model, flags)
        plan = {"fold": fold + 1, "training_files": [str(data["files"][i]) for i in training],
                "held_out_files": [str(data["files"][i]) for i in held_out],
                "K": K.tolist(), "distortion": D.ravel().tolist(),
                "distortion_health": distortion_health(K, D, data["image_size"]), "pose_groups": []}
        for view in _views(data, held_out, model):
            index, mask = view["photo"], view["mask"]
            anchor, evaluation = mask & anchor_pattern, mask & ~anchor_pattern
            if np.any(anchor & evaluation) or anchor.sum() < 6 or evaluation.sum() < 4:
                raise AssertionError("Anchor/evaluation split is invalid")
            success, rotation, translation = cv.solvePnP(
                data["object_points"][index][anchor], data["image_points"][index][anchor], K, D, flags=cv.SOLVEPNP_ITERATIVE
            )
            if not success:
                raise ValueError("Estimasi pose pada foto validasi gagal")
            projected, _ = cv.projectPoints(data["object_points"][index][evaluation], rotation, translation, K, D)
            observed = data["image_points"][index][evaluation]
            errors, _ = error_metrics(observed, projected)
            plan["pose_groups"].append({"file": str(data["files"][index]), "panel": view["panel"],
                                        "anchor_indices": np.flatnonzero(anchor).tolist(),
                                        "evaluation_indices": np.flatnonzero(evaluation).tolist(),
                                        "rvec": rotation.ravel().tolist(), "tvec_mm": translation.ravel().tolist()})
            for point, error, obs, pred in zip(np.flatnonzero(evaluation), errors, observed[:, 0], projected[:, 0]):
                rows.append({"file": str(data["files"][index]), "point_index": int(point), "fold": fold + 1,
                             "observed_u": float(obs[0]), "observed_v": float(obs[1]),
                             "projected_u": float(pred[0]), "projected_v": float(pred[1]), "error_px": float(error)})
        plans.append(plan)
    return rows, plans


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _study_candidate(data, detector, model, output, flags=0, lens_model="standard5"):
    output.mkdir(parents=True)
    views, rms, K, D, rotations, translations = _fit(data, range(len(data["files"])), model, flags)
    training_rows = []
    for view, rotation, translation in zip(views, rotations, translations):
        projected, _ = cv.projectPoints(view["object"], rotation, translation, K, D)
        errors, _ = error_metrics(view["image"], projected)
        for point, error in zip(np.flatnonzero(view["mask"]), errors):
            training_rows.append({"file": str(data["files"][view["photo"]]), "point_index": int(point), "error_px": float(error)})
    held_rows, plans = _cross_validate(data, model, flags=flags)
    training_errors = np.array([r["error_px"] for r in training_rows])
    held_errors = np.array([r["error_px"] for r in held_rows])
    if not np.isclose(np.sqrt(np.mean(training_errors ** 2)), rms, atol=1e-4):
        raise AssertionError("Recomputed RMS mismatch")
    result = {"detector": detector, "model": model, "lens_model": lens_model, "calibration_flags": int(flags),
              "photos": len(data["files"]), "pose_count": len(views),
              "training_points": len(training_rows), "training_mean_px": float(training_errors.mean()), "training_rms_px": float(rms),
              "validation_points": len(held_rows), "validation_mean_px": float(held_errors.mean()),
              "validation_rms_px": float(np.sqrt(np.mean(held_errors ** 2))), "K": K.tolist(), "distortion": D.ravel().tolist(),
              "distortion_health": distortion_health(K, D, data["image_size"])}
    np.savez_compressed(output / "parameters.npz", K=K, distortion=D, rvecs=np.array(rotations), tvecs=np.array(translations),
                        files=data["files"], image_points=data["image_points"], object_points=data["object_points"],
                        view_photo_indices=np.array([v["photo"] for v in views]), view_masks=np.array([v["mask"] for v in views]),
                        image_size=data["image_size"], square_size_mm=data["square_size_mm"])
    (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output / "validation_plan.json").write_text(json.dumps(plans, indent=2), encoding="utf-8")
    _write_csv(output / "training_errors.csv", training_rows)
    _write_csv(output / "validation_errors.csv", held_rows)
    return result


def run_panel_study(config, photos, output):
    if config["inner_corners"] != [7, 7]:
        raise ValueError("Eksperimen ini khusus pola 7x7 yang telah diaudit orientasi sambungannya")
    orientation = json.loads((ROOT / "config/board_panels.json").read_text(encoding="utf-8"))["images"]
    manifest = json.loads((ROOT / config["dataset_manifest"]).read_text(encoding="utf-8"))
    hashes = {r["file"]: r["sha256"] for r in manifest["images"]}
    files = find_images(photos)
    if {f.name for f in files} != set(orientation):
        raise ValueError("Eksperimen membutuhkan seluruh foto yang orientasi panelnya tercatat pada board_panels.json")
    for path in files:
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes.get(path.name):
            raise ValueError(f"Foto berubah; orientasi panel perlu diaudit ulang: {path.name}")
    reference = calibrate(config, photos, output / "baseline_reference", "baseline")
    with np.load(output / "baseline_reference/parameters.npz", allow_pickle=False) as z:
        data = {k: z[k].copy() for k in z.files}
    data["axes"] = [orientation[str(name)] for name in data["files"]]
    candidate = {**data, "image_points": data["image_points"].copy()}
    (output / "correlation_audit").mkdir()
    (output / "correlation_corners").mkdir()
    source_paths = {p.name: p for p in files}
    for i, name in enumerate(data["files"]):
        parts = panel_masks(data["valid_mask"][i], data["axes"][i])
        # Keep the same grayscale conversion as the baseline for a controlled comparison.
        gray = cv.cvtColor(cv.imread(str(source_paths[str(name)])), cv.COLOR_BGR2GRAY)
        measured, diagnostics = correlation_corners(gray, data["image_points"][i], parts[0] | parts[1])
        candidate["image_points"][i] = measured
        (output / "correlation_audit" / f"{Path(str(name)).stem}.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
        display = cv.cvtColor(gray, cv.COLOR_GRAY2BGR)
        for index, pt in enumerate(measured[:, 0]):
            color = (0, 180, 0) if (parts[0] | parts[1])[index] else (0, 165, 255)
            cv.circle(display, tuple(np.round(pt).astype(int)), 6, color, -1)
        cv.imwrite(str(output / "correlation_corners" / str(name)), cv.resize(display, (780, 1040)))
    results = []
    for detector, inputs in (("local_corner", data), ("checker_correlation", candidate)):
        for model in ("single_plane", "two_panels"):
            print(f"Menguji {detector} + {model}, validasi silang 5 bagian...", flush=True)
            result = _study_candidate(inputs, detector, model, output / f"{detector}_{model}")
            results.append(result)
            print(f"  Mean {result['training_mean_px']:.6f}, RMS {result['training_rms_px']:.6f}; validasi mean {result['validation_mean_px']:.6f}, RMS {result['validation_rms_px']:.6f} px", flush=True)
    # All variants must evaluate exactly the same point identities, not just counts.
    identity_sets = []
    for result in results:
        folder = output / f"{result['detector']}_{result['model']}"
        with (folder / "validation_errors.csv").open() as handle:
            identities = [(row["file"], int(row["point_index"])) for row in csv.DictReader(handle)]
        if len(identities) != len(set(identities)):
            raise AssertionError("Validation point repeated")
        identity_sets.append(set(identities))
    if not all(ids == identity_sets[0] for ids in identity_sets):
        raise AssertionError("Validation point identities differ between models")
    summary = {"results": results, "same_validation_observations": True, "folds": 5,
               "observations_used": results[0]["training_points"], "validation_observations": len(identity_sets[0]),
               "versions": reference["versions"], "square_size_mm": config["square_size_mm"],
               "note": "All photos retained. Center seam excluded uniformly by physical geometry, not residuals. All variants use the same nonseam point identities. Two-panel model adds six pose parameters per photo. Cross-validation is internal and is not independent metrology validation."}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _report_study(summary, output)
    return summary


def _report_study(summary, output):
    import matplotlib.pyplot as plt
    results = summary["results"]
    labels = [f"{r['detector']}\n{r['model']}" for r in results]
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(results))
    ax.bar(x-0.18, [r["training_mean_px"] for r in results], width=0.36, label="Mean data kalibrasi")
    ax.bar(x+0.18, [r["validation_mean_px"] for r in results], width=0.36, label="Mean validasi silang")
    ax.set_xticks(x, labels)
    ax.set(ylabel="Mean error (px)", title="Perbandingan pada titik non-sambungan yang sama")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "comparison.png", dpi=160)
    plt.close(fig)
    lines = ["# Eksperimen metode pengurangan error", "",
             "Seluruh 29 foto dipertahankan. Garis sudut di celah tengah dikecualikan secara seragam berdasarkan geometri fisik papan, "
             f"bukan berdasarkan error. Dengan pengecualian ambigu terdahulu, tersisa {summary['observations_used']} titik non-sambungan yang sama pada semua varian.", "",
             "| Detektor | Model | Pose | Mean latih (px) | RMS latih (px) | Mean validasi (px) | RMS validasi (px) |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for r in results:
        lines.append(f"| {r['detector']} | {r['model']} | {r['pose_count']} | {r['training_mean_px']:.6f} | {r['training_rms_px']:.6f} | {r['validation_mean_px']:.6f} | {r['validation_rms_px']:.6f} |")
    lines += ["", "## Arti metode", "",
              "- local_corner: pengukuran hasil audit sebelumnya.",
              "- checker_correlation: mencocokkan pola empat kuadran terang/gelap pada citra, dengan puncak korelasi diinterpolasi subpiksel. Titik tidak disalin dari proyeksi kamera.",
              "- single_plane: kedua sisi diasumsikan satu bidang datar dengan satu pose per foto.",
              "- two_panels: tiap sisi papan lipat dianggap bidang tersendiri, dengan K/distorsi bersama dan dua pose per foto. 58 pose bukan 58 foto; jumlah foto tetap 29.", "",
              "## Validasi dan batas kesimpulan", "",
              "Validasi silang lima bagian menahan seluruh foto dari estimasi K/distorsi. Pada foto tertahan, pose hanya dihitung dari titik jangkar berselang-seling; error dihitung pada titik lain yang tidak dipakai untuk pose. "
              f"Identitas {summary['validation_observations']} titik evaluasi sama di semua varian. Daftar foto training/tertahan serta indeks jangkar/evaluasi tersimpan di validation_plan.json; residual tiap titik ada di validation_errors.csv.", "",
              "Model dua panel memiliki enam parameter pose tambahan per foto, sehingga penurunan error latih saja bukan bukti perbaikan. Hasil validasi silang memberi pemeriksaan tambahan, "
              "tetapi tetap berasal dari dataset yang sama dan metode dipilih setelah percobaan. Ini belum membuktikan akurasi pada data pengukuran independen.", "",
              "Metode ini adalah pengembangan atas kalibrasi papan datar pada materi: tiap panel tetap diperlakukan sebagai target planar. "
              "Jangan menyajikannya sebagai prosedur identik dengan contoh satu papan. Baseline perkuliahan tetap tersedia dan tidak diganti otomatis.", "",
              "Mean dan RMS harus dibaca terpisah. Mean di bawah 1 px belum berarti memenuhi acuan <0,5 px pada materi, terutama jika RMS masih sekitar atau di atas 1 px.", "",
              "![Perbandingan](comparison.png)", ""]
    text = "\n".join(lines)
    (output / "report.md").write_text(text, encoding="utf-8")
    from os.path import relpath
    relative = Path(relpath(output, ROOT / "reports")).as_posix()
    (ROOT / "reports/alternatives.md").write_text(text.replace("](comparison.png)", f"]({relative}/comparison.png)") + f"\n[Hasil lengkap]({relative}/summary.json)\n", encoding="utf-8")
