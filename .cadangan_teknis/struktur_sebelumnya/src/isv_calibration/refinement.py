"""Controlled follow-up experiments, including negative and unsafe results."""
import json
from pathlib import Path

import cv2 as cv
import numpy as np

from .calibration import ROOT
from .alternatives import run_panel_study, panel_masks, correlation_corners, _study_candidate


def _load_reference(reference):
    with np.load(reference / "baseline_reference/parameters.npz", allow_pickle=False) as source:
        data = {k: source[k].copy() for k in source.files}
    orientation = json.loads((ROOT / "config/board_panels.json").read_text(encoding="utf-8"))["images"]
    data["axes"] = [orientation[str(name)] for name in data["files"]]
    return data


def _measure(data, photos, output, label, scale, panelwise):
    folder = output / "measurement_audit" / label
    folder.mkdir(parents=True)
    sources = {p.name: p for p in photos.rglob("*") if p.is_file()}
    result = {**data, "image_points": data["image_points"].copy()}
    for i, name in enumerate(data["files"]):
        gray = cv.cvtColor(cv.imread(str(sources[str(name)])), cv.COLOR_BGR2GRAY)
        parts = panel_masks(data["valid_mask"][i], data["axes"][i])
        diagnostics = []
        if panelwise:
            for mask in parts:
                measured, audit = correlation_corners(gray, data["image_points"][i], mask,
                                                      pixels_per_square=scale, homography_valid=mask)
                result["image_points"][i][mask] = measured[mask]
                diagnostics.extend(audit)
        else:
            result["image_points"][i], diagnostics = correlation_corners(
                gray, data["image_points"][i], parts[0] | parts[1], pixels_per_square=scale
            )
        (folder / f"{Path(str(name)).stem}.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    return result


def run_refinement_study(config, photos, output):
    reference_folder = output / "reference_methods"
    reference = run_panel_study(config, photos, reference_folder)
    original = _load_reference(reference_folder)
    with np.load(reference_folder / "checker_correlation_two_panels/parameters.npz", allow_pickle=False) as saved:
        base_correlation = {**original, "image_points": saved["image_points"].copy()}
    results = []
    locations = []
    cache = {"global100": base_correlation}
    for label, scale, panelwise in (("global200", 200, False), ("panel100", 100, True), ("panel200", 200, True)):
        print(f"Mengukur sudut {label}...", flush=True)
        measured = _measure(original, photos, output, label, scale, panelwise)
        cache[label] = measured
        result = _study_candidate(measured, label, "two_panels", output / label)
        result["stage"] = "measurement"
        results.append(result)
        locations.append(label)
    for label, flags, lens in (
        ("fixed_k3", cv.CALIB_FIX_K3, "four_active_coefficients"),
        ("rational8", cv.CALIB_RATIONAL_MODEL, "rational8"),
        ("thin_prism9", cv.CALIB_THIN_PRISM_MODEL, "polynomial5_plus_prism4"),
        ("rational_prism12", cv.CALIB_RATIONAL_MODEL | cv.CALIB_THIN_PRISM_MODEL, "rational8_plus_prism4"),
    ):
        print(f"Menguji model distorsi {label}...", flush=True)
        result = _study_candidate(base_correlation, "global100", "two_panels", output / label, flags, lens)
        result["stage"] = "distortion"
        results.append(result)
        locations.append(label)
    label = "global200_thin_prism9"
    print(f"Menguji kombinasi {label}...", flush=True)
    result = _study_candidate(cache["global200"], "global200", "two_panels", output / label,
                              cv.CALIB_THIN_PRISM_MODEL, "polynomial5_plus_prism4")
    result["stage"] = "combined"
    results.append(result)
    locations.append(label)
    reference_point_ids = None
    import csv
    for location, result in zip(locations, results):
        result["experiment_id"] = location
        for file, expected in (("training_errors.csv", 1216), ("validation_errors.csv", 579)):
            with (output / location / file).open() as stream:
                identities = [(row["file"], int(row["point_index"])) for row in csv.DictReader(stream)]
            if len(identities) != expected or len(set(identities)) != expected:
                raise AssertionError("Jumlah/identitas titik eksperimen berubah")
            key = file
            if reference_point_ids is None:
                reference_point_ids = {}
            if key not in reference_point_ids:
                reference_point_ids[key] = set(identities)
            if set(identities) != reference_point_ids[key]:
                raise AssertionError("Perbandingan tidak memakai identitas titik yang sama")
        print(f"{location}: mean {result['training_mean_px']:.6f}; RMS {result['training_rms_px']:.6f}; validasi mean {result['validation_mean_px']:.6f}; RMS {result['validation_rms_px']:.6f}", flush=True)
    summary = {"reference_methods": reference, "follow_up_results": results,
               "square_size_mm": config["square_size_mm"], "photos": 29,
               "training_points": 1216, "validation_points": 579, "folds": 5,
               "acquisition": json.loads((ROOT / "config/acquisition.json").read_text(encoding="utf-8")),
               "limitations": "Method selection reuses internal cross-validation. No independent test set; automatic focus reported by user. A lower training error alone is insufficient."}
    (output / "refinement_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_refinement_report(summary, output)
    from os.path import relpath
    (ROOT / "reports/refinement_run.json").write_text(json.dumps({"output": Path(relpath(output, ROOT)).as_posix()}, indent=2), encoding="utf-8")
    from .evolution_report import build_evolution_report
    print(f"Laporan perkembangan: {build_evolution_report(output)}", flush=True)
    return summary


def write_refinement_report(summary, output):
    import matplotlib.pyplot as plt
    baseline = summary["reference_methods"]["results"][-1]
    rows = [{**baseline, "experiment_id": "global100_standard5"}] + summary["follow_up_results"]
    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(rows))
    ax.bar(x-0.18, [r["training_mean_px"] for r in rows], .36, label="Mean kalibrasi")
    ax.bar(x+0.18, [r["validation_mean_px"] for r in rows], .36, label="Mean validasi silang")
    ax.set_xticks(x, [r["experiment_id"] for r in rows], rotation=30, ha="right")
    ax.set(ylabel="Mean error (px)", title="Pengujian lanjutan pada 1.216 titik yang sama")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "refinement_comparison.png", dpi=160)
    plt.close(fig)
    lines = ["# Pengujian metode lanjutan", "",
             "Semua varian memakai 29 foto, 1.216 titik non-sambungan dan 579 titik evaluasi validasi silang yang sama. Tidak ada titik dibuang berdasarkan residual.", "",
             "| Eksperimen | Mean latih | RMS latih | Mean validasi | RMS validasi | Pemeriksaan pole |",
             "|---|---:|---:|---:|---:|---|"]
    for row in rows:
        health = row["distortion_health"]
        unsafe = health["pole_within_approximate_sensor_extent"] or health["nonpositive_or_nonfinite_jacobian_fraction"] > 0
        decision = "Pole/pembalikan pemetaan pada grid uji" if unsafe else "Lolos pemeriksaan numerik terbatas"
        lines.append(f"| {row['experiment_id']} | {row['training_mean_px']:.6f} | {row['training_rms_px']:.6f} | {row['validation_mean_px']:.6f} | {row['validation_rms_px']:.6f} | {decision} |")
    lines += ["", "global200 menaikkan resolusi perataan menjadi 200 piksel/kotak tanpa mengubah luas template fisik. panel100/panel200 memakai inisialisasi homografi per panel. "
              "Model distorsi dibandingkan dengan titik citra yang sama: k3 dikunci nol, rational delapan koefisien, thin-prism tanpa rational (sembilan koefisien aktif), "
              "serta gabungan rational+prism (12 aktif). global200_thin_prism9 menggabungkan resolusi tinggi dengan model prism tanpa denominator rational.", "",
              "Model rational mempunyai denominator 1+k4*r²+k5*r⁴+k6*r⁶. Akar positif menandakan titik singular. Radius sudut sensor dihitung secara perkiraan dari K; "
              "pemeriksaan ini bukan bukti lengkap invertibilitas, tetapi alasan untuk tidak merekomendasikan model yang mempunyai pole di area tersebut.", "",
              "Pengguna mengonfirmasi kamera/zoom sama, fokus otomatis, dan pose kamera bervariasi. Variasi pose memang diperlukan. Perubahan intrinsik akibat autofocus "
              "mungkin terjadi pada sebagian kamera, tetapi pengaruhnya pada dataset ini belum diukur. Fokus terkunci diperlukan untuk pengambilan ulang yang lebih terkendali.", "",
              "Pemilihan metode memakai validasi internal yang telah dipakai berkali-kali. Hasil bukan estimasi tak-bias pada data baru; seluruh percobaan, termasuk yang tidak membantu, harus dilaporkan.", "",
              "![Perbandingan lanjutan](refinement_comparison.png)", ""]
    text = "\n".join(lines)
    (output / "refinement_report.md").write_text(text, encoding="utf-8")
    from os.path import relpath
    relative = Path(relpath(output, ROOT / "reports")).as_posix()
    (ROOT / "reports/refinement.md").write_text(text.replace("](refinement_comparison.png)", f"]({relative}/refinement_comparison.png)") + f"\n[Data lengkap]({relative}/refinement_summary.json)\n", encoding="utf-8")
