"""Tugas ISV. Cukup jalankan: python mulai.py

Alur tetap: deteksi -> audit -> dua panel -> korelasi -> resolusi -> hasil akhir.
Tidak ada pilihan mode atau program tahap terpisah.
"""
from pathlib import Path
import csv
import hashlib
import json
import os
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def siapkan():
    """Buat lingkungan lokal otomatis agar teman cukup menjalankan satu perintah."""
    if sys.version_info < (3, 10):
        raise RuntimeError("Gunakan Python 3.10 atau lebih baru.")
    lingkungan = ROOT / ".venv"
    python = lingkungan / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if Path(sys.prefix).resolve() == lingkungan.resolve():
        import importlib.util
        if any(importlib.util.find_spec(nama) is None for nama in ("cv2", "numpy", "matplotlib", "reportlab")):
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True, cwd=ROOT)
        return True
    if not python.is_file():
        if lingkungan.exists() and not (lingkungan / "pyvenv.cfg").is_file():
            raise RuntimeError("Folder .venv bukan lingkungan Python; tidak akan ditimpa.")
        print("Menyiapkan Python dan kebutuhan program...", flush=True)
        venv.EnvBuilder(with_pip=True).create(lingkungan)
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--timeout", "30", "--retries", "1", "-r", str(ROOT / "requirements.txt")], check=True, cwd=ROOT)
    subprocess.run([str(python), str(ROOT / "mulai.py")], check=True, cwd=ROOT)
    return False


def pustaka():
    global cv, np, plt, CRITERIA
    import cv2 as cv
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    CRITERIA = (cv.TERM_CRITERIA_EPS + cv.TERM_CRITERIA_MAX_ITER, 60, .001)
    cv.setNumThreads(4)
    cv.setRNGSeed(0)


def error_metrics(observed, projected):
    residuals = (observed-projected).reshape(-1, 2)
    return np.linalg.norm(residuals, axis=1), residuals


def remeasure(gray, initial, pattern=(7, 7)):
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
    detection, refinement = gray, gray
    dimensions = ((cols + 3) * 100, (rows + 3) * 100)
    warp = cv.warpPerspective(detection, M, dimensions)
    # Refinement uses non-CLAHE intensities in both coordinate systems.
    refine_warp = warp
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
        "profile": "baseline",
        "homography_inliers_for_initialization_only": int(inliers.sum()),
        "local_corner_response_offsets": evidence,
        "final_refinement_movement_px": movement.tolist(),
        "final_refinement_applied": accepted.tolist(),
        "coordinate_system": "original image pixels",
    }


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
        parts = [data["valid_mask"][index]] if model == "whole_board" else panel_masks(data["valid_mask"][index], data["axes"][index])
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
    output.mkdir(parents=True, exist_ok=True)
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
    np.savez_compressed(output / "parameter.npz", K=K, distortion=D, rvecs=np.array(rotations), tvecs=np.array(translations),
                        files=data["files"], image_points=data["image_points"], object_points=data["object_points"],
                        view_photo_indices=np.array([v["photo"] for v in views]), view_masks=np.array([v["mask"] for v in views]),
                        image_size=data["image_size"], square_size_mm=data["square_size_mm"])
    (output / "hasil.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output / "rencana_validasi.json").write_text(json.dumps(plans, indent=2), encoding="utf-8")
    _write_csv(output / "galat_kalibrasi.csv", training_rows)
    _write_csv(output / "galat_validasi.csv", held_rows)
    return result


def baca_foto():
    """Tahap pertama: foto asli dibaca ulang; sudut awal bukan hasil akhir."""
    pengaturan = json.loads((ROOT / "data/pengaturan.json").read_text(encoding="utf-8"))
    sumber = ROOT / "foto"
    daftar = sorted(sumber.glob("*.jpg"))
    acuan = {r["file"]: r for r in pengaturan["images"]}
    if {p.name for p in daftar} != set(acuan):
        raise ValueError("Isi folder foto berbeda dari dataset tugas yang disiapkan.")
    with np.load(ROOT / "data/sudut_awal.npz", allow_pickle=False) as simpanan:
        awal = {str(n): p.copy() for n, p in zip(simpanan["files"], simpanan["image_points"])}
    objek = np.zeros((49, 3), np.float32)
    objek[:, :2] = np.mgrid[:7, :7].T.reshape(-1, 2) * pengaturan["square_size_mm"]
    titik, mask, ukuran, catatan = [], [], None, []
    folder = ROOT / "audit/01_deteksi"
    (folder / "titik").mkdir(parents=True, exist_ok=True)
    (folder / "pemeriksaan").mkdir(exist_ok=True)
    for path in daftar:
        if hashlib.sha256(path.read_bytes()).hexdigest() != acuan[path.name]["sha256"]:
            raise ValueError(f"Foto berubah: {path.name}. Gunakan foto asli dataset tugas.")
        gambar = cv.imread(str(path))
        if gambar is None:
            raise ValueError(f"Foto tidak dapat dibaca: {path.name}")
        gray = cv.cvtColor(gambar, cv.COLOR_BGR2GRAY)
        if ukuran is None:
            ukuran = gray.shape[::-1]
        if gray.shape[::-1] != ukuran:
            raise ValueError("Resolusi foto tidak seragam.")
        corners, rincian = remeasure(gray, awal[path.name])
        valid = np.ones(49, dtype=bool)
        for e in pengaturan["excluded_points"]:
            if e["file"] == path.name:
                valid[e["index"]] = False
        titik.append(corners)
        mask.append(valid)
        cv.drawChessboardCorners(gambar, (7, 7), corners, True)
        for p in corners[~valid, 0]:
            cv.circle(gambar, tuple(np.round(p).astype(int)), 25, (0, 165, 255), 4)
        cv.imwrite(str(folder / "titik" / path.name), cv.resize(gambar, (780, 1040)))
        (folder / "pemeriksaan" / f"{path.stem}.json").write_text(json.dumps(rincian, indent=2), encoding="utf-8")
        catatan.append({"file": path.name, "sha256": acuan[path.name]["sha256"], "points_used": int(valid.sum())})
    _write_csv(folder / "foto_digunakan.csv", catatan)
    data = {"files": np.array([p.name for p in daftar]), "image_points": np.array(titik),
            "object_points": np.array([objek] * len(daftar)), "valid_mask": np.array(mask),
            "image_size": np.array(ukuran), "square_size_mm": np.array(pengaturan["square_size_mm"]),
            "axes": [pengaturan["panel_axes"][p.name] for p in daftar]}
    return pengaturan, data


def ukur_korelasi(data, resolusi):
    hasil = {**data, "image_points": data["image_points"].copy()}
    for i, nama in enumerate(data["files"]):
        gray = cv.cvtColor(cv.imread(str(ROOT / "foto" / str(nama))), cv.COLOR_BGR2GRAY)
        kiri, kanan = panel_masks(data["valid_mask"][i], data["axes"][i])
        hasil["image_points"][i], _ = correlation_corners(gray, data["image_points"][i], kiri | kanan,
                                                        pixels_per_square=resolusi)
    return hasil


def buat_visualisasi(pengaturan):
    """Gambar penjelas dari hasil tersimpan; tidak mengubah kalibrasi."""
    folder = ROOT / "audit/06_hasil_akhir"
    with np.load(ROOT / "audit/01_deteksi/parameter.npz", allow_pickle=False) as z:
        files, awal = z["files"].copy(), z["image_points"].copy()
    with np.load(folder / "parameter.npz", allow_pickle=False) as z:
        akhir = {k: z[k].copy() for k in z.files}
    nama = "Kalibrasi_27.jpg"  # Contoh tetap, bukan dipilih berdasarkan error.
    i = list(files).index(nama)
    rgb = cv.cvtColor(cv.imread(str(ROOT / "foto" / nama)), cv.COLOR_BGR2RGB)
    pts = awal[i].reshape(-1, 2)
    ukur = akhir["image_points"][i].reshape(-1, 2)
    grid = np.mgrid[:7, :7].T.reshape(-1, 2).astype(np.float32)
    H, _ = cv.findHomography(grid, pts, cv.RANSAC, 8.0)
    batas = cv.perspectiveTransform(np.float32([[[-1,-1],[7,-1],[7,7],[-1,7],[-1,-1]]]), H)[0]
    valid = np.ones(49, dtype=bool)
    for e in pengaturan["excluded_points"]:
        if e["file"] == nama: valid[e["index"]] = False
    a, b = panel_masks(valid, pengaturan["panel_axes"][nama])
    dipakai = a | b
    proyeksi = np.full((49, 2), np.nan)
    for v in np.flatnonzero(akhir["view_photo_indices"] == i):
        mask = akhir["view_masks"][v]
        q, _ = cv.projectPoints(akhir["object_points"][i][mask], akhir["rvecs"][v],
                                akhir["tvecs"][v], akhir["K"], akhir["distortion"])
        proyeksi[mask] = q.reshape(-1, 2)
    low, high = batas.min(axis=0)-90, batas.max(axis=0)+90
    def foto(ax, judul):
        ax.imshow(rgb);ax.set_xlim(low[0],high[0]);ax.set_ylim(high[1],low[1])
        ax.set_title(judul, fontsize=12);ax.axis("off")
    def simpan(fig, nama):
        fig.tight_layout(pad=1.4)
        path = folder / nama
        fig.savefig(path, dpi=180, facecolor="white");plt.close(fig)
        return path
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 6.4))
    axes[0].imshow(rgb)
    axes[0].set_title(f"A. Foto utuh ({rgb.shape[1]} x {rgb.shape[0]} px)", fontsize=11)
    axes[0].axis("off")
    foto(axes[1], "B. Area papan diperbesar")
    seleksi = simpan(fig, "Visual_Seleksi_Area.png")
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 8.1))
    foto(axes[0,0], "A. Foto asli (dipotong untuk tampilan)")
    foto(axes[0,1], "B. Perkiraan batas + 49 sudut dalam")
    axes[0,1].plot(*batas.T, color="yellow", lw=2)
    axes[0,1].scatter(*pts.T, s=10, color="#00ffff")
    foto(axes[1,0], "C. Dua panel; celah tidak dipakai")
    for mask, warna, label in [(a,"#00ffff","Panel A"),(b,"#ff55dd","Panel B"),(~dipakai,"#ffad00","Dikecualikan")]:
        axes[1,0].scatter(*pts[mask].T, s=15, c=warna, label=label)
    axes[1,0].legend(fontsize=8, loc="lower left")
    foto(axes[1,1], "D. Pengukuran akhir dan proyeksi model")
    axes[1,1].scatter(*ukur[dipakai].T, s=24, facecolors="none", edgecolors="#00ff66", label="Ukur: lingkaran")
    axes[1,1].scatter(*proyeksi[dipakai].T, s=12, c="#ff4040", marker="x", label="Proyeksi: silang")
    axes[1,1].legend(fontsize=8, loc="lower left")
    alur = simpan(fig, "Visual_Proses.png")
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 6.8))
    gray = cv.cvtColor(rgb, cv.COLOR_RGB2GRAY)
    for ax, skala in zip(axes[0], [100, 200]):
        W = np.float64([[skala,0,2*skala],[0,skala,2*skala],[0,0,1]])
        warp = cv.warpPerspective(gray, W @ np.linalg.inv(H), (10*skala,10*skala))
        ax.imshow(warp, cmap="gray", vmin=0, vmax=255)
        ax.set_xlim(skala,9*skala);ax.set_ylim(9*skala,skala)
        ax.set_title(f"Perataan pencarian: {skala} px/kotak", fontsize=11);ax.axis("off")
    galat = np.linalg.norm(proyeksi[dipakai]-ukur[dipakai], axis=1)
    j = np.flatnonzero(dipakai)[np.argsort(galat)[len(galat)//2]]
    ax = axes[1,0];ax.imshow(rgb)
    ax.scatter(*ukur[j], s=100, facecolors="none", edgecolors="#00ff66", linewidths=2, label="Ukur")
    ax.scatter(*proyeksi[j], s=65, c="#ff4040", marker="x", linewidths=2, label="Proyeksi")
    ax.plot([ukur[j,0],proyeksi[j,0]], [ukur[j,1],proyeksi[j,1]], color="yellow")
    ax.set_xlim(ukur[j,0]-12,ukur[j,0]+12);ax.set_ylim(ukur[j,1]+12,ukur[j,1]-12)
    ax.set_title(f"Sudut #{j+1}: jarak {np.linalg.norm(proyeksi[j]-ukur[j]):.3f} px", fontsize=11)
    ax.tick_params(labelsize=7);ax.set_xlabel("Koordinat foto asli (px)",fontsize=8);ax.legend(fontsize=8)
    ax = axes[1,1];foto(ax, "Arah selisih proyeksi (panah x30)")
    delta = (proyeksi[dipakai]-ukur[dipakai])*30
    ax.scatter(*ukur[dipakai].T, s=7, c="#00ff66")
    ax.quiver(*ukur[dipakai].T, *delta.T, angles="xy", scale_units="xy", scale=1,
              color="#ff4040", width=.005)
    detail = simpan(fig, "Visual_Detail.png")
    (folder / "Visual_Keterangan.json").write_text(json.dumps({
        "file": nama, "corner_index_zero_based": int(j), "corner_error_px": float(np.linalg.norm(proyeksi[j]-ukur[j])),
        "example_selection": "fixed filename; corner nearest median error in this photo",
        "arrows_scale": 30, "boundary": "homography extrapolation from internal grid; not measured outer edge",
        "residuals": "training residuals; not independent validation",
    }, indent=2), encoding="utf-8")
    # Respons pencarian ditampilkan dari piksel dan parameter yang sama dengan proses ukur.
    fig, axes = plt.subplots(2, 2, figsize=(8.4, 7.6))
    axes[0,0].imshow(gray, cmap="gray", vmin=0, vmax=255)
    axes[0,0].set_xlim(low[0], high[0]);axes[0,0].set_ylim(high[1], low[1])
    axes[0,0].set_title("A. Citra keabuan: sumber pengukuran", fontsize=11);axes[0,0].axis("off")
    W = np.float64([[100,0,200],[0,100,200],[0,0,1]])
    warp = cv.warpPerspective(gray, W @ np.linalg.inv(H), (1000,1000))
    response = cv.cornerMinEigenVal(cv.GaussianBlur(warp,(7,7),1.5),7,3)
    axes[0,1].imshow(response, cmap="inferno")
    axes[0,1].set_xlim(100,900);axes[0,1].set_ylim(900,100)
    axes[0,1].set_title("B. Respons sudut: terang = lebih kuat", fontsize=11);axes[0,1].axis("off")
    for ax, skala in zip(axes[1], [100,200]):
        W = np.float64([[skala,0,2*skala],[0,skala,2*skala],[0,0,1]])
        warp = cv.warpPerspective(gray, W @ np.linalg.inv(H), (10*skala,10*skala))
        size, radius = 2*round(.16*skala), round(.24*skala)
        half = radius+size//2
        x,y = np.round((grid[j]+2)*skala).astype(int)
        patch = warp[y-half:y+half,x-half:x+half].astype(np.float32)
        u = np.arange(size)-(size-1)/2
        xx,yy = np.meshgrid(u,u);template = np.sign(xx*yy).astype(np.float32)
        score = np.abs(cv.matchTemplate(patch,template,cv.TM_CCOEFF_NORMED))
        iy,ix = np.unravel_index(np.argmax(score),score.shape)
        heat = ax.imshow(score, cmap="viridis", vmin=0, vmax=1)
        ax.scatter(ix,iy,marker="+",s=140,c="white",linewidths=2)
        ax.set_title(f"{'C' if skala==100 else 'D'}. Korelasi {skala} px/kotak; puncak {score[iy,ix]:.3f}", fontsize=10)
        ax.set_xlabel("Posisi pencarian lokal", fontsize=9);ax.tick_params(labelsize=8)
        fig.colorbar(heat, ax=ax, fraction=.046, pad=.04)
    lokalisasi = simpan(fig, "Visual_Lokalisasi.png")
    return nama, seleksi, alur, detail, lokalisasi


def buat_laporan(pengaturan, tahap):
    """Laporan visual: satu halaman per bagian dengan keterangan singkat."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, Spacer, PageBreak, Flowable
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus.tableofcontents import TableOfContents
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from html import escape
    import matplotlib
    import zipfile
    font = Path(matplotlib.get_data_path()) / "fonts/ttf"
    for nama, berkas in [("Isi","DejaVuSans.ttf"),("Judul","DejaVuSans-Bold.ttf")]:
        pdfmetrics.registerFont(TTFont(nama,str(font/berkas)))
    isi = ParagraphStyle("Isi",fontName="Isi",fontSize=10,leading=14,spaceAfter=9)
    judul = ParagraphStyle("Judul",fontName="Judul",fontSize=15,leading=20,spaceAfter=12)
    kecil = ParagraphStyle("Kecil",parent=isi,fontSize=8,leading=11,spaceAfter=5)
    folder = ROOT / "laporan";folder.mkdir(exist_ok=True)
    audit = ROOT / "audit/06_hasil_akhir"
    akhir = tahap[-1]
    contoh, seleksi, alur, detail, lokalisasi = buat_visualisasi(pengaturan)
    with zipfile.ZipFile(ROOT / "audit/Riwayat_Audit.zip") as z:
        studi = json.loads(z.read("pengujian_metode_lengkap/refinement_summary.json"))
    labels = ["k1","k2","p1","p2","k3","s1","s2","s3","s4"]
    D = [akhir["distortion"][i] for i in [0,1,2,3,4,8,9,10,11]]
    def simpan(fig,nama):
        fig.tight_layout(pad=1.8)
        path = audit/nama;fig.savefig(path,dpi=180,facecolor="white");plt.close(fig)
        return path
    fig, axes = plt.subplots(2,2,figsize=(8.4,7.4))
    x = np.arange(6);ax=axes[0,0]
    ax.bar(x-.18,[r["training_mean_px"] for r in tahap],.36,label="Kalibrasi")
    ax.bar(x+.18,[r["validation_mean_px"] for r in tahap],.36,label="Validasi silang")
    ax.set_xticks(x,[f"T{i}" for i in range(1,7)]);ax.set_ylabel("Mean error (px)")
    ax.set_title("A. Pengaruh enam tahap",fontsize=12);ax.legend(fontsize=8)
    ax=axes[0,1];ax.axis("off");ax.set_title("B. Matriks intrinsik K (piksel)",fontsize=12)
    matriks="\n".join("["+" ".join(f"{v:9.3f}" for v in row)+"]" for row in akhir["K"])
    ax.text(.03,.65,matriks,fontsize=10.5,family="monospace",va="center",transform=ax.transAxes)
    ax.text(.03,.27,"fx, fy: fokus dalam piksel\ncx, cy: koordinat titik utama",fontsize=10,transform=ax.transAxes)
    ax=axes[1,0];bars=ax.bar(labels,D,color="#155e75")
    ax.axhline(0,color="black",lw=.5);ax.bar_label(bars,fmt="%.3f",fontsize=7,padding=2)
    ax.set_title("C. Sembilan koefisien distorsi aktif",fontsize=11)
    ax.tick_params(axis="x",labelsize=8);ax.margins(y=.23)
    ax=axes[1,1];ax.axis("off");ax.set_title("D. Evaluasi model akhir",fontsize=12)
    metrik=[["Metrik","Piksel"],["Mean kalibrasi",f"{akhir['training_mean_px']:.6f}"],
            ["RMS kalibrasi",f"{akhir['training_rms_px']:.6f}"],
            ["Mean validasi silang",f"{akhir['validation_mean_px']:.6f}"],
            ["RMS validasi silang",f"{akhir['validation_rms_px']:.6f}"]]
    t=ax.table(cellText=metrik,colWidths=[.65,.35],cellLoc="left",loc="center")
    t.auto_set_font_size(False);t.set_fontsize(10);t.scale(1,1.8)
    for (row,col),cell in t.get_celld().items():
        cell.set_edgecolor("#cad8df")
        if row==0:cell.set_facecolor("#e8f0f5")
    hasil = simpan(fig,"Visual_Hasil.png")
    # Grafik audit lama tetap tersedia sebagai berkas mandiri.
    fig,ax=plt.subplots(figsize=(9,4))
    ax.bar(x-.18,[r["training_mean_px"] for r in tahap],.36,label="Mean kalibrasi")
    ax.bar(x+.18,[r["validation_mean_px"] for r in tahap],.36,label="Mean validasi silang")
    ax.set_xticks(x,[f"Tahap {i}" for i in range(1,7)]);ax.set_ylabel("Error (piksel)")
    ax.legend();fig.tight_layout();fig.savefig(ROOT/"audit/Urutan_Hasil.png",dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,3));bars=ax.bar(labels,D,color="#155e75")
    ax.axhline(0,color="black",lw=.5);ax.bar_label(bars,fmt="%.4f",fontsize=8,padding=3)
    ax.margins(y=.2);ax.set_title("Koefisien distorsi hasil akhir")
    fig.tight_layout();fig.savefig(audit/"Distorsi.png",dpi=160);plt.close(fig)
    ref=studi["reference_methods"]["results"]
    uji={r["experiment_id"]:r for r in studi["follow_up_results"]}
    fig,axes=plt.subplots(2,2,figsize=(8.4,7.8))
    def batang(ax,nama,nilai,warna,judul):
        ax.barh(nama,nilai,color=warna,height=.6);ax.invert_yaxis()
        ax.set_xlim(0,max(nilai)*1.26);ax.set_title(judul,fontsize=11)
        ax.tick_params(axis="y",labelsize=8);ax.tick_params(axis="x",labelsize=8)
        ax.set_xlabel("Mean validasi silang (px)",fontsize=9)
        for i,v in enumerate(nilai):ax.text(v+max(nilai)*.02,i,f"{v:.4f}",va="center",fontsize=8)
    batang(axes[0,0],["Sudut / 1 bidang","Sudut / 2 panel","Korelasi / 1 bidang","Korelasi / 2 panel"],
           [r["validation_mean_px"] for r in ref],["#718096","#155e75","#718096","#155e75"],"A. Geometri dan pengukuran")
    batang(axes[0,1],["Global 100","Per panel 100","Global 200","Per panel 200"],
           [ref[-1]["validation_mean_px"]]+[uji[k]["validation_mean_px"] for k in ["panel100","global200","panel200"]],
           ["#718096","#718096","#155e75","#718096"],"B. Resolusi perataan (px/kotak)")
    batang(axes[1,0],["k3 = 0","Standar 5","Rational 8","Thin-prism 9","Rational + prism 12*"],
           [uji["fixed_k3"]["validation_mean_px"],ref[-1]["validation_mean_px"]]+[uji[k]["validation_mean_px"] for k in ["rational8","thin_prism9","rational_prism12"]],
           ["#718096","#718096","#718096","#155e75","#c2413b"],"C. Model distorsi pada resolusi 100")
    ax=axes[1,1];h=pengaturan["history"]
    yy=np.arange(2)
    ax.bar(yy-.18,[h[3]["mean_px"],h[4]["mean_px"]],.36,label="Mean")
    ax.bar(yy+.18,[h[3]["rms_px"],h[4]["rms_px"]],.36,label="RMS")
    ax.set_xticks(yy,["Dasar","+ Gaussian/CLAHE"]);ax.tick_params(labelsize=8)
    ax.set_ylabel("Error (px)");ax.set_title("D. Uji prapengolahan tambahan",fontsize=11);ax.legend(fontsize=8)
    alternatif=simpan(fig,"Visual_Eksperimen.png")
    ringkasan=[{"tahap":i,"nama":r["nama"],"foto":r["photos"],"titik":r["training_points"],
                "mean_px":r["training_mean_px"],"rms_px":r["training_rms_px"],
                "mean_validasi_px":r["validation_mean_px"],"rms_validasi_px":r["validation_rms_px"],
                "titik_validasi":r["validation_points"]} for i,r in enumerate(tahap,1)]
    _write_csv(ROOT/"audit/Urutan_Hasil.csv",ringkasan)
    (ROOT/"audit/Urutan_Hasil.json").write_text(json.dumps(tahap,indent=2),encoding="utf-8")
    cerita=[]
    judul_bagian = ParagraphStyle("JudulBagian",parent=judul,keepWithNext=True)
    keterangan = ParagraphStyle("JudulGambar",parent=isi,fontSize=9,leading=12,alignment=1,spaceBefore=6,spaceAfter=10,keepWithNext=True)
    daftar_style = ParagraphStyle("Daftar",parent=isi,fontSize=10,leading=17,leftIndent=18,firstLineIndent=-18,rightIndent=30,spaceBefore=7)
    sampul = ParagraphStyle("Sampul",parent=judul,fontSize=21,leading=29,alignment=1,textColor=colors.HexColor("#153e55"))
    tengah = ParagraphStyle("Tengah",parent=isi,alignment=1,leading=17)
    def p(teks,style=isi):cerita.append(Paragraph(escape(teks),style))
    # Bagian awal tidak memuat identitas penulis/institusi yang belum diberikan.
    cerita.append(Spacer(1,125))
    p("LAPORAN PRAKTIKUM MANDIRI",tengah)
    cerita.append(Spacer(1,16))
    p("KALIBRASI KAMERA",sampul)
    p("Instrumentasi Sistem Visual",tengah)
    cerita.append(Spacer(1,40))
    p("Dokumentasi visual pengolahan citra, pengembangan metode, dan evaluasi galat reproyeksi",tengah)
    cerita.append(Spacer(1,55))
    p("29 foto papan catur | 7 x 7 sudut dalam",tengah)
    p("Ukuran sisi kotak: 44 mm",tengah)
    p("Materi acuan: Pertemuan 10",tengah)
    cerita.append(PageBreak())
    p("DAFTAR ISI",judul)
    class DaftarRapi(TableOfContents):
        # Entri tetap dikumpulkan otomatis; kolom halaman dan titik penghubung
        # digambar langsung agar seragam pada kedua daftar.
        def wrap(self,availWidth,availHeight):
            self._listing=self._lastEntries or [(0,"Menyusun daftar",0,None)]
            self.width=availWidth;self.height=32*len(self._listing)
            return self.width,self.height
        def drawOn(self,canvas,x,y,_sW=0):
            Flowable.drawOn(self,canvas,x,y,_sW)
        def draw(self):
            c=self.canv;c.setFont("Isi",10)
            for i,(_,teks,page,key) in enumerate(self._listing):
                y=self.height-16-32*i
                nomor=str(self.formatter(page) if self.formatter else page)
                c.setFillColor(colors.HexColor("#17252f"));c.drawString(0,y,teks)
                c.drawRightString(self.width,y,nomor)
                kiri=pdfmetrics.stringWidth(teks,"Isi",10)+8
                kanan=self.width-pdfmetrics.stringWidth(nomor,"Isi",10)-8
                dot=" . ";dw=pdfmetrics.stringWidth(dot,"Isi",10)
                c.setFillColor(colors.HexColor("#647580"))
                c.drawString(kiri,y,dot*max(0,int((kanan-kiri)/dw)))
                if key:c.linkRect("",key,(0,y-3,self.width,y+12),relative=1)
    daftar_isi=DaftarRapi(formatter=lambda n: "ii" if n==3 else str(n-3));daftar_isi.levelStyles=[daftar_style]
    daftar_isi.dotsMinLevel=0
    cerita.append(daftar_isi)
    cerita.append(PageBreak())
    heading=Paragraph("DAFTAR GAMBAR",judul)
    heading._entry=("TOCEntry","Daftar Gambar","daftar-gambar")
    cerita.append(heading)
    daftar_gambar=DaftarRapi(formatter=lambda n: str(n-3));daftar_gambar._notifyKind="FigureEntry"
    daftar_gambar.levelStyles=[daftar_style];daftar_gambar.dotsMinLevel=0
    cerita.append(daftar_gambar)
    gambar_ke=0
    captions=["Foto utuh dan pembesaran area papan catur",
              "Alur pengukuran sudut dan pemisahan dua panel",
              "Respons sudut dan korelasi pola pada dua resolusi",
              "Perataan citra dan visualisasi galat reproyeksi",
              "Perkembangan error, matriks intrinsik, dan distorsi",
              "Perbandingan modifikasi dan pemilihan model kalibrasi"]
    def halaman(judul_halaman,gambar,tinggi,teks):
        nonlocal gambar_ke
        cerita.append(PageBreak())
        heading=Paragraph(escape(judul_halaman),judul_bagian)
        heading._entry=("TOCEntry",judul_halaman,f"bagian-{gambar_ke+1}")
        cerita.append(heading)
        if gambar_ke==0:
            p("Kalibrasi kamera dilakukan untuk menentukan hubungan antara posisi titik pada papan dan posisi piksel pada foto. Hubungan tersebut diperlukan agar citra dapat digunakan sebagai dasar pengukuran geometrik. Pada praktikum ini, matriks intrinsik K dan koefisien distorsi ditentukan melalui pengolahan foto papan catur. Kesesuaian model kemudian dinilai menggunakan galat reproyeksi, yaitu jarak antara titik hasil pengukuran dan proyeksi model.")
        cerita.append(Image(str(gambar),width=510,height=tinggi))
        gambar_ke+=1
        caption=f"Gambar {gambar_ke}. {captions[gambar_ke-1]}"
        cp=Paragraph(escape(caption),keterangan)
        cp._entry=("FigureEntry",caption,f"gambar-{gambar_ke}")
        cerita.append(cp)
        for baris in teks:p(baris)
    halaman("1. Pendahuluan dan Data Pengamatan",seleksi,365,[
        f"Data yang digunakan terdiri atas 29 foto beresolusi 3120 x 4160 piksel dengan ukuran sisi kotak 44 mm. Pada setiap foto disediakan 49 sudut dalam dari susunan 7 x 7 titik. Foto {contoh} ditampilkan secara utuh dan diperbesar pada Gambar 1 agar bagian papan yang diamati dapat dikenali. Pemotongan hanya diterapkan untuk memperjelas tampilan dalam laporan. Pengukuran tetap dilakukan dalam koordinat dan resolusi foto asli."])
    halaman("2. Tahapan Pengukuran dan Pemodelan Papan",alur,492,[
        "Pada Gambar 2, posisi 49 sudut dalam ditentukan dari pertemuan kotak terang dan gelap. Batas berwarna kuning diperkirakan dari susunan sudut tersebut sehingga tidak digunakan sebagai hasil pengukuran tepi secara langsung. Setelah pemeriksaan citra, tiga sudut yang tidak dapat ditentukan dengan yakin akibat pantulan atau celah dikecualikan sehingga tersisa 1.418 pengamatan. Seluruh titik pada garis sambungan kemudian diabaikan dengan aturan yang sama pada setiap foto, sehingga 1.216 pengamatan dari seluruh 29 foto tetap digunakan. Kedua sisi papan dimodelkan sebagai dua panel dengan posisi dan orientasi masing-masing, tetapi matriks intrinsik serta koefisien distorsinya ditetapkan bersama. Titik ukur berwarna hijau selanjutnya dibandingkan dengan proyeksi model yang ditandai silang merah."])
    halaman("3. Pengolahan Citra dan Penentuan Sudut",lokalisasi,461,[
        "Pengukuran sudut diawali dengan mengubah foto menjadi citra keabuan sebagaimana ditampilkan pada Gambar 3. Respons sudut lokal digunakan untuk mencari persilangan, kemudian koordinatnya disempurnakan dengan cornerSubPix agar dapat dinyatakan sebagai pecahan piksel. Pada tahap berikutnya, posisi sudut ditentukan melalui korelasi ternormalisasi terhadap pola empat kuadran terang dan gelap; tanda putih menunjukkan puncak respons yang diperoleh. Kerapatan perataan dinaikkan dari 100 menjadi 200 piksel per kotak untuk menguji pengaruh sampling terhadap hasil pencarian. Peningkatan ini tidak menambah resolusi sensor karena seluruh informasi tetap berasal dari foto yang sama. Koordinat hasil pencarian kemudian dikembalikan ke piksel foto asli sebelum digunakan dalam kalibrasi."])
    halaman("4. Evaluasi Galat Reproyeksi",detail,413,[
        "Pada Gambar 4, citra diratakan sementara untuk membantu pencarian sudut, tanpa mengubah asumsi tentang bentuk fisik papan. Galat reproyeksi dihitung sebagai jarak antara titik ukur pada foto dan titik yang diproyeksikan oleh model kamera. Pembesaran satu sudut diperlihatkan untuk menunjukkan jarak lingkaran hijau terhadap silang merah dalam piksel asli. Sudut contoh dipilih berdasarkan galat yang paling dekat dengan median pada foto tersebut. Panah pada gambar diperpanjang 30 kali agar arah selisih dapat dilihat, sedangkan angka galat tetap dihitung dari jarak sebenarnya. Karena parameter model diperoleh dari data yang juga ditampilkan, gambar ini menunjukkan residual kalibrasi dan belum menjadi pengujian terhadap data independen."])
    halaman("5. Hasil Kalibrasi Bertahap",hasil,449,[
        f"Perubahan galat pada enam tahap, matriks intrinsik, dan koefisien distorsi ditampilkan pada Gambar 5. Tahap pertama menggunakan 1.418 pengamatan, sedangkan tahap kedua hingga keenam menggunakan 1.216 identitas titik yang sama setelah garis sambungan dikecualikan. Pada model akhir diperoleh mean galat {akhir['training_mean_px']:.6f} piksel dan RMS {akhir['training_rms_px']:.6f} piksel; mean merupakan rata-rata jarak, sedangkan RMS merupakan akar rata-rata kuadrat jarak. Validasi silang dilakukan dengan membagi foto menjadi lima kelompok, kemudian posisi dan orientasi pada foto uji ditentukan dari titik jangkar yang terpisah dari 579 titik evaluasi. Mean validasi silang yang diperoleh sebesar {akhir['validation_mean_px']:.6f} piksel, tetapi pemilihan metode masih menggunakan dataset yang sama secara berulang. Hasil ini belum memenuhi acuan galat di bawah 0,50 piksel pada materi dan belum membuktikan akurasi pengukuran panjang secara independen."])
    halaman("6. Pembahasan Perubahan Metode",alternatif,458,[
        "Berdasarkan perbandingan pada Gambar 6, penggunaan dua panel memberikan penurunan galat terbesar dalam rangkaian pengujian ini, dengan konsekuensi bertambahnya enam parameter posisi dan orientasi per foto. Perataan global pada 200 piksel per kotak dipertahankan karena hasil validasinya lebih baik daripada perataan per panel yang diuji. Pada korelasi 100 piksel per kotak, thin-prism dengan sembilan koefisien aktif dipilih dibandingkan kombinasi rational dan thin-prism yang menghasilkan validasi lebih buruk serta pemetaan distorsi yang tidak stabil pada sebagian domain sensor perkiraan. Penambahan Gaussian dan CLAHE pada pengujian historis juga tidak memberikan perbaikan sehingga tidak diterapkan sebagai pengolahan tambahan pada alur akhir. Model akhir disusun dengan menggabungkan pengukuran korelasi global 200 piksel per kotak dan distorsi thin-prism. Meskipun residual berkurang, hasil tersebut belum membuktikan besar ketidaksebidangan papan atau penyebab fisik distorsi lensa karena keduanya tidak diukur secara terpisah."])
    p("Acuan: materi/Pertemuan_10.pdf, hlm. 45-54 dan 57-60. Data hasil: audit/Urutan_Hasil.json dan Riwayat_Audit.zip. Pergantian detector dapat mengubah koordinat ukur; validasi berulang belum menggantikan pengujian independen.",kecil)
    cerita.append(Paragraph('Dasar metode: Zhang (2000), <link href="https://doi.org/10.1109/34.888718" color="#155e75">DOI 10.1109/34.888718</link>; <link href="https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html" color="#155e75">dokumentasi model OpenCV</link>.',kecil))
    def footer(c,doc):
        if doc.page==1:
            c.addPageLabel(0,prefix="Sampul")
            return
        if doc.page==2:c.addPageLabel(1,style="ROMAN_LOWER",start=1)
        if doc.page==4:c.addPageLabel(3,style="ARABIC",start=1)
        c.setFont("Isi",7);c.setFillColor(colors.HexColor("#526572"))
        c.drawString(40,23,"Instrumentasi Sistem Visual | Kalibrasi kamera | 29 foto")
        nomor={2:"i",3:"ii"}.get(doc.page,str(doc.page-3))
        c.drawRightString(A4[0]-40,23,nomor)
    class LaporanVisual(SimpleDocTemplate):
        def afterFlowable(self,flowable):
            if not hasattr(flowable,"_entry"):return
            kind,teks,key=flowable._entry
            nomor=self.page
            self.canv.bookmarkPage(key)
            if kind=="TOCEntry":self.canv.addOutlineEntry(teks,key,0,False)
            self.notify(kind,(0,escape(teks),nomor,key))
    LaporanVisual(str(folder/"Laporan.pdf"),pagesize=A4,leftMargin=40,rightMargin=40,topMargin=35,
                  bottomMargin=43,title="Kalibrasi Kamera - Laporan Visual").multiBuild(
                  cerita,onFirstPage=footer,onLaterPages=footer)
    md=["# Kalibrasi Kamera - Ringkasan", "", "Laporan PDF dimulai dengan sampul, daftar isi, dan daftar gambar; dilanjutkan enam halaman isi dengan Gambar 1-6, paragraf naratif, dan nomor halaman otomatis.", "",
        "| Tahap | Modifikasi | Mean px | RMS px | Mean CV |", "|---|---|---:|---:|---:|"]
    md += [f"| T{i} | {r['nama']} | {r['training_mean_px']:.4f} | {r['training_rms_px']:.4f} | {r['validation_mean_px']:.4f} |" for i,r in enumerate(tahap,1)]
    md += ["", "Mean akhir belum memenuhi acuan <0,50 px. Validasi masih internal.", "", "29 foto dinamai Kalibrasi_01.jpg sampai Kalibrasi_29.jpg. Pemetaan nama asli dan hash: data/Identitas_Foto.csv.",
           "", "Jalankan python mulai.py. Foto, audit, pemetaan nama, dan laporan tidak di-ignore Git.", ""]
    (folder/"Ringkasan.md").write_text("\n".join(md),encoding="utf-8")


def kerjakan():
    print("1/6 Mengukur dan memeriksa sudut pada foto...", flush=True)
    pengaturan, awal = baca_foto()
    (ROOT / "audit/Catatan_Data.json").write_text(json.dumps({"square_size_mm": pengaturan["square_size_mm"],
        "acquisition": pengaturan["acquisition"], "excluded_points": pengaturan["excluded_points"],
        "versions": {"python": sys.version.split()[0], "opencv": cv.__version__, "numpy": np.__version__}}, indent=2), encoding="utf-8")
    tahap = []
    def simpan(nomor, nama, data, model, flags=0, lens="standard5"):
        lokasi = ROOT / "audit" / nama
        hasil = _study_candidate(data, "local_corner" if nomor < 4 else "checker_correlation", model, lokasi, flags, lens)
        hasil["nama"] = judul[nomor-1]
        hasil["nomor_tahap"] = nomor
        hasil["versions"] = {"python": sys.version.split()[0], "opencv": cv.__version__, "numpy": np.__version__}
        (lokasi / "hasil.json").write_text(json.dumps(hasil, indent=2), encoding="utf-8")
        tahap.append(hasil)
    judul = ["Deteksi dan audit sudut", "Abaikan garis sambungan", "Model dua panel",
             "Korelasi pola", "Resolusi lebih tinggi", "Model distorsi akhir"]
    simpan(1, "01_deteksi", awal, "whole_board")
    print("2/6 Memisahkan titik pada celah sambungan...", flush=True)
    simpan(2, "02_tanpa_sambungan", awal, "single_plane")
    print("3/6 Menghitung dua panel papan...", flush=True)
    simpan(3, "03_dua_panel", awal, "two_panels")
    print("4/6 Mengukur ulang dengan korelasi pola...", flush=True)
    korelasi = ukur_korelasi(awal, 100)
    simpan(4, "04_korelasi", korelasi, "two_panels")
    print("5/6 Meningkatkan resolusi pengukuran...", flush=True)
    resolusi = ukur_korelasi(awal, 200)
    simpan(5, "05_resolusi", resolusi, "two_panels")
    print("6/6 Menghitung hasil akhir dan membuat laporan...", flush=True)
    simpan(6, "06_hasil_akhir", resolusi, "two_panels", cv.CALIB_THIN_PRISM_MODEL, "polynomial5_plus_prism4")
    bukti = ROOT / "audit/06_hasil_akhir/titik"
    bukti.mkdir(exist_ok=True)
    for i, nama in enumerate(awal["files"]):
        gambar = cv.imread(str(ROOT / "foto" / str(nama)))
        a,b = panel_masks(awal["valid_mask"][i], awal["axes"][i]);valid = a|b
        for j, point in enumerate(resolusi["image_points"][i,:,0]):
            warna = (0, 180, 0) if valid[j] else (0,165,255)
            cv.circle(gambar, tuple(np.round(point).astype(int)), 7, warna, -1)
        cv.imwrite(str(bukti / str(nama)), cv.resize(gambar, (780,1040)))
    buat_laporan(pengaturan, tahap)
    print(f"Selesai. Buka: {ROOT / 'laporan/Laporan.pdf'}", flush=True)
    print(f"Mean {tahap[-1]['training_mean_px']:.3f} px; RMS {tahap[-1]['training_rms_px']:.3f} px.", flush=True)


if __name__ == "__main__":
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
    try:
        if len(sys.argv) > 1:
            raise ValueError("Tidak perlu pilihan mode. Cukup jalankan: python mulai.py")
        if siapkan():
            pustaka()
            kerjakan()
    except (OSError, ValueError, RuntimeError, ImportError, subprocess.CalledProcessError) as kesalahan:
        print(f"Program berhenti: {kesalahan}", file=sys.stderr)
        raise SystemExit(1)
