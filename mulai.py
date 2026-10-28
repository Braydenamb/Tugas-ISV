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


def buat_laporan(pengaturan, tahap):
    """Hasil belajar berupa satu ringkasan dan satu PDF, tanpa pilihan laporan."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Image, Preformatted, Spacer, PageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from html import escape
    import matplotlib
    font = Path(matplotlib.get_data_path()) / "fonts/ttf"
    pdfmetrics.registerFont(TTFont("Isi", str(font / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("Judul", str(font / "DejaVuSans-Bold.ttf")))
    isi = ParagraphStyle("Isi", fontName="Isi", fontSize=9, leading=13, spaceAfter=8)
    kecil = ParagraphStyle("Kecil", parent=isi, fontSize=7.6, leading=10.5, spaceAfter=0)
    judul = ParagraphStyle("Judul", fontName="Judul", fontSize=13, leading=18, spaceBefore=8, spaceAfter=10)
    kode = ParagraphStyle("Kode", fontName="Courier", fontSize=9.5, leading=14, spaceAfter=8)
    folder = ROOT / "laporan"
    folder.mkdir(exist_ok=True)
    akhir = tahap[-1]
    fig, ax = plt.subplots(figsize=(9, 4))
    x = np.arange(6)
    ax.bar(x-.18, [r["training_mean_px"] for r in tahap], .36, label="Mean kalibrasi")
    ax.bar(x+.18, [r["validation_mean_px"] for r in tahap], .36, label="Mean validasi silang")
    ax.set_xticks(x, [f"Tahap {i}" for i in range(1, 7)])
    ax.set(ylabel="Error (piksel)", title="Pengerjaan berurutan dari deteksi sampai hasil akhir")
    ax.legend();fig.tight_layout()
    grafik_tahap = ROOT / "audit/Urutan_Hasil.png"
    fig.savefig(grafik_tahap, dpi=160);plt.close(fig)
    label = ["k1", "k2", "p1", "p2", "k3", "s1", "s2", "s3", "s4"]
    angka = [akhir["distortion"][j] for j in [0, 1, 2, 3, 4, 8, 9, 10, 11]]
    fig, ax = plt.subplots(figsize=(8, 3))
    bars = ax.bar(label, angka, color="#155e75")
    ax.axhline(0, color="black", lw=.5);ax.bar_label(bars, fmt="%.4f", padding=3, fontsize=8)
    ax.margins(y=.2);ax.set(title="Koefisien distorsi hasil akhir", ylabel="Koefisien")
    fig.tight_layout();grafik_distorsi = ROOT / "audit/06_hasil_akhir/Distorsi.png"
    fig.savefig(grafik_distorsi, dpi=160);plt.close(fig)
    ringkasan = [{"tahap": i, "nama": r["nama"], "foto": r["photos"], "titik": r["training_points"],
                  "mean_px": r["training_mean_px"], "rms_px": r["training_rms_px"],
                  "mean_validasi_px": r["validation_mean_px"], "rms_validasi_px": r["validation_rms_px"],
                  "titik_validasi": r["validation_points"]} for i, r in enumerate(tahap, 1)]
    _write_csv(ROOT / "audit/Urutan_Hasil.csv", ringkasan)
    (ROOT / "audit/Urutan_Hasil.json").write_text(json.dumps(tahap, indent=2), encoding="utf-8")
    rows = [["Tahap", "Perubahan", "Titik", "Mean px", "RMS px", "Mean CV"]]
    rows += [[str(i), r["nama"], str(r["training_points"]), f"{r['training_mean_px']:.4f}", f"{r['training_rms_px']:.4f}", f"{r['validation_mean_px']:.4f}"] for i, r in enumerate(tahap, 1)]
    cerita = []
    def p(teks, style=isi):cerita.append(Paragraph(escape(teks).replace("\n", "<br/>"), style))
    def tabel(data, widths):
        t = Table([[Paragraph(escape(str(v)), kecil) for v in row] for row in data], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e8f0f5")),
                              ("VALIGN", (0,0), (-1,-1), "TOP"), ("TOPPADDING", (0,0), (-1,-1), 5),
                              ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                              ("LINEBELOW", (0,0), (-1,-1), .25, colors.HexColor("#cad8df"))]))
        cerita.extend([t, Spacer(1, 9)])
    p("Tugas Mandiri ISV - Kalibrasi Kamera", judul)
    p("Tujuan: memperoleh matriks intrinsik K, plot distorsi, dan mean reprojection error sesuai materi Pertemuan 10. Data: 29 foto, 3120 x 4160 piksel, papan 8 x 8 kotak (7 x 7 sudut dalam), sisi kotak 44 mm.")
    p("1. Urutan pengerjaan", judul)
    tabel(rows, [42,183,55,78,78,79])
    cerita.append(Image(str(grafik_tahap), width=500, height=222))
    p("Tahap 1 memakai 1.418 pengamatan setelah tiga sudut ambigu dikecualikan berdasarkan citra. Tahap 2 mengabaikan semua titik di celah tengah secara seragam, sehingga tersisa 1.216 titik. Tahap 2-6 memakai identitas titik dan 579 titik evaluasi yang sama; tahap 1 memiliki jumlah titik berbeda. CV berarti validasi silang.")
    p("Pengukuran sudut tetap berasal dari gambar. Homografi hanya membantu pencarian; koordinat dikembalikan ke piksel foto asli. Tidak ada titik dipindahkan ke tebakan model atau dibuang berdasarkan besarnya error.")
    cerita.append(PageBreak())
    p("2. Hasil akhir", judul)
    p(f"Seluruh 29 foto dipakai. Mean error {akhir['training_mean_px']:.6f} piksel; RMS {akhir['training_rms_px']:.6f} piksel. Mean validasi silang {akhir['validation_mean_px']:.6f}; RMS validasi {akhir['validation_rms_px']:.6f} piksel.")
    p("Matriks intrinsik K dalam piksel:")
    cerita.append(Preformatted("\n".join("["+" ".join(f"{v:12.5f}" for v in row)+"]" for row in akhir["K"]), kode))
    tabel([["Koefisien", "Nilai"]]+[[n,f"{v:.9f}"] for n,v in zip(label,angka)], [180,335])
    cerita.append(Image(str(grafik_distorsi), width=490, height=184))
    p("Model akhir menggunakan dua panel planar dengan K dan distorsi bersama. Setiap foto memiliki dua pose; 58 pose tetap berasal dari 29 foto. Model thin-prism menambah empat koefisien s1-s4; koefisien rational k4-k6 tetap nol. Pengembangan ini perlu dijelaskan sebagai penyesuaian atas contoh satu papan datar pada materi.")
    cerita.append(PageBreak())
    p("3. Penjelasan, audit, dan batas hasil", judul)
    p("Tahap 1 memperbaiki posisi sudut pada foto. Tahap 2 memisahkan pengaruh celah papan. Tahap 3 memperlakukan kedua sisi sebagai bidang tersendiri. Tahap 4 mengukur sudut dari korelasi empat kuadran terang-gelap. Tahap 5 meningkatkan resolusi perataan dari 100 menjadi 200 piksel per kotak. Tahap 6 menambah suku thin-prism pada model distorsi.")
    p("Validasi silang memakai lima bagian foto. Foto yang diuji tidak dipakai untuk mengestimasi K/distorsi. Pada foto tersebut, pose dihitung dari titik jangkar berselang-seling; error diukur pada titik lain. Pemilihan metode menggunakan data yang sama berkali-kali, sehingga ini masih validasi internal dan belum bukti akurasi pada pengukuran independen.")
    p("Tiga sudut ambigu: WA0101 baris 7 kolom 4 (celah/pantulan), WA0089 baris 7 kolom 7 dan WA0094 baris 6 kolom 3 (pantulan/tekstur). Garis sambungan di tengah dikecualikan seluruhnya pada tahap 2-6, termasuk satu dari tiga titik tersebut. Mask titik dan alasan pengecualian tersimpan dalam data dan parameter audit.")
    p("Menurut acuan materi hlm. 53, error <0,25 px sangat bagus dan <0,50 px dapat diterima. Hasil sekitar 0,739 px belum mencapai acuan <0,5 px. Kamera dan zoom dilaporkan sama, fokus otomatis dan pose bervariasi. Fokus otomatis mungkin memengaruhi intrinsik, tetapi kontribusinya pada error ini belum dibuktikan. Seluruh pengerjaan tetap memakai foto yang tersedia.")
    p("4. Cara membaca berkas", judul)
    p("Buka laporan/Laporan.pdf untuk hasil utama. Folder audit/01 sampai audit/06 mengikuti urutan pada tabel. Setiap tahap menyimpan angka, parameter, error tiap titik, dan rencana validasi. Foto bertanda ada pada tahap 1 dan 6. Riwayat audit serta percobaan sebelumnya tetap disertakan dalam audit/Riwayat_Audit.zip dan ikut Git; arsip itu tidak perlu dibuka untuk menjalankan tugas.")
    p("Cukup jalankan: python mulai.py. Program menyiapkan kebutuhan dan menjalankan seluruh tahap dalam urutan tetap. Hasil yang sudah disertakan bisa dibaca tanpa menjalankan ulang. Percobaan lama yang tidak membantu/ditolak tetap tersedia dalam arsip audit; tidak ada pilihan cabang yang harus ditentukan pengguna.")
    p("Referensi: Yakub Fahim Luckyarno, Optika Geometri Kamera & Kalibrasi Sensorik, Pertemuan 10, hlm. 45-54, 57-60 dan 65 (materi/Pertemuan_10.pdf). Contoh materi mencetak keluaran calibrateCamera sebagai mean, sedangkan nilai baliknya RMS. Program menghitung mean jarak secara terpisah melalui projectPoints dan melaporkan keduanya.")
    def footer(c, doc):
        c.setFont("Isi", 7);c.setFillColor(colors.HexColor("#526572"))
        c.drawString(40, 23, "Tugas ISV | 29 foto | Kotak 44 mm")
        c.drawRightString(A4[0]-40, 23, str(doc.page))
    SimpleDocTemplate(str(folder / "Laporan.pdf"), pagesize=A4, leftMargin=40, rightMargin=40,
                      topMargin=35, bottomMargin=43, title="Tugas Mandiri ISV - Kalibrasi Kamera").build(cerita, onFirstPage=footer, onLaterPages=footer)
    md = ['# Hasil Tugas Mandiri ISV', '', 'Jalankan `python mulai.py`, lalu buka `laporan/Laporan.pdf`.', '',
          '| Tahap | Perubahan | Titik | Mean px | RMS px | Mean CV |', '|---|---|---:|---:|---:|---:|']
    md += ['| '+' | '.join(r)+' |' for r in rows[1:]]
    md += ['', 'Tahap 2-6 memakai 1.216 titik yang sama. Mean dan RMS berbeda; hasil masih belum memenuhi acuan <0,5 px.', '',
           'Semua audit ikut Git pada folder `audit/`. Riwayat lama ada dalam `audit/Riwayat_Audit.zip`.', '',
           'Kamera dan zoom sama, fokus otomatis, pose bervariasi menurut keterangan pengguna. Kontribusi autofocus belum diukur.', '']
    (folder / "Ringkasan.md").write_text('\n'.join(md), encoding='utf-8')


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
