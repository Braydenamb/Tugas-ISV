from pathlib import Path
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def write_outputs(result, residuals, output):
    plt.rcParams.update({"font.size": 10, "figure.dpi": 140})
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(result["distortion_names"], result["distortion"], color="#155e75")
    ax.axhline(0, color="black", lw=0.6)
    ax.bar_label(bars, fmt="%.5f", padding=4)
    ax.margins(y=0.2)
    ax.set(title=f"Koefisien distorsi ({result['profile']})", ylabel="Koefisien tanpa satuan")
    fig.tight_layout()
    fig.savefig(output / "distortion.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 4))
    rows = result["per_photo"]
    ax.bar(range(len(rows)), [row["mean_error_px"] for row in rows], color="#155e75")
    ax.axhline(result["mean_reprojection_error_px"], color="#b45309", label=f"Mean global = {result['mean_reprojection_error_px']:.4f} px")
    ax.set_xticks(range(len(rows)), [r["file"].split("WA")[-1].split(".")[0] for r in rows], rotation=90)
    ax.set(ylabel="Mean error (px)", xlabel="Nomor akhir nama foto", title="Error per foto")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "errors_per_photo.png")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(residuals[:, 0], residuals[:, 1], s=5, alpha=0.4)
    ax.axhline(0, color="black", lw=0.5)
    ax.axvline(0, color="black", lw=0.5)
    ax.set(xlabel="Residual u (px)", ylabel="Residual v (px)", title="Residual titik citra - proyeksi")
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    fig.savefig(output / "residuals.png")
    plt.close(fig)
    write_report(result, output, output / "report.md")


def write_report(result, output, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    prefix = Path(os.path.relpath(output, target.parent)).as_posix()
    root = Path(__file__).resolve().parents[2]
    reference = Path(os.path.relpath(root / "references/Pertemuan_10.pdf", target.parent)).as_posix()
    K = "\n".join("[" + " ".join(f"{x:13.6f}" for x in row) + "]" for row in result["K"])
    lines = [
        "# Hasil kalibrasi kamera", "",
        f"Profil: **{result['profile']}**. Ukuran kotak: **{result['square_size_mm']:g} mm**. "
        f"Foto dipakai: **{result['images_used']}/{result['images_total']}**. "
        f"Titik dipakai: **{result['observations_used']}**.", "",
        "## Metode", "",
        f"Acuan: [materi Pertemuan 10]({reference}), hlm. 45-54, 57-60 dan 65. "
        "Objek dimodelkan pada Z=0 dengan jarak antarsudut sesuai ukuran kotak. "
        "Kalibrasi menggunakan pasangan titik objek/citra dan cv2.calibrateCamera; "
        "projectPoints digunakan untuk menghitung error.", "",
        "Pemrosesan tambahan membantu pengukuran sudut dan dijelaskan sebagai penyesuaian atas contoh materi. "
        "Inisialisasi dataset hanya dipakai bila hash foto cocok. Foto lain dideteksi melalui findChessboardCorners "
        "atau findChessboardCornersSB. Homografi hanya menentukan wilayah pencarian; koordinat akhir "
        "berasal dari respons sudut citra, dikembalikan ke piksel foto asli, dan diperhalus subpiksel. "
        "Tidak ada titik digeser ke proyeksi model atau dibuang menggunakan ambang error kalibrasi.", "",
        "Profil baseline memakai tahap pengukuran hasil audit sebelumnya. Profil mild menambahkan Gaussian "
        "3x3 (sigma 0,8) dan CLAHE (clipLimit 1,5; grid 8x8) untuk pencarian. Refinement akhir memakai "
        "intensitas tanpa CLAHE. Keduanya tetap memakai koordinat dan ukuran foto asli.", "",
        "## Matriks intrinsik K (piksel)", "", "```text", K, "```", "",
        "## Koefisien distorsi", "", "| Koefisien | Nilai |", "|---|---:|",
    ]
    lines += [f"| {name} | {value:.9f} |" for name, value in zip(result["distortion_names"], result["distortion"])]
    lines += ["", f"![Koefisien distorsi]({prefix}/distortion.png)", "", "## Error reproyeksi", "",
              f"- Mean: **{result['mean_reprojection_error_px']:.6f} piksel**.",
              f"- RMS: **{result['rms_reprojection_error_px']:.6f} piksel**.", "",
              "Mean = rata-rata jarak Euclidean pengamatan terhadap proyeksi. RMS = akar rata-rata kuadrat jarak tersebut. "
              "Nilai balik calibrateCamera adalah RMS; keduanya dilaporkan terpisah karena istilah pada contoh materi hlm. 59-60 tidak konsisten.", "",
              f"![Error per foto]({prefix}/errors_per_photo.png)", "",
              "| Foto | Titik | Mean (px) | RMS (px) |", "|---|---:|---:|---:|"]
    lines += [f"| {row['file']} | {row['points_used']} | {row['mean_error_px']:.4f} | {row['rms_error_px']:.4f} |" for row in result["per_photo"]]
    lines += ["", "## Pengamatan yang dikecualikan", ""]
    if result["excluded_points"]:
        lines += [f"- {e['file']}, baris {e['row']} kolom {e['col']}: {e['reason']}" for e in result["excluded_points"]]
    else:
        lines += ["Tidak ada pengecualian titik yang berlaku pada foto dalam run ini."]
    lines += ["", "## Batas interpretasi", "",
              "Materi hlm. 53 menggunakan acuan <0,25 px sangat bagus, <0,50 px dapat diterima dan >1 px perlu kalibrasi ulang. "
              "Ini acuan kuliah, bukan ambang universal untuk semua resolusi/kamera. Error lebih kecil pada data kalibrasi "
              "tidak membuktikan akurasi pada data baru. Sambungan, ketidakrataan papan, pantulan dan ketidakseragaman kotak "
              "tidak dapat diperbaiki secara fisik melalui CLAHE atau blur. Pengambilan ulang dengan papan datar-kaku "
              "dan konfigurasi kamera tetap masih diperlukan bila target akurasi belum tercapai.", "",
              f"Lingkungan: Python {result['versions']['python']}, OpenCV {result['versions']['opencv']}, NumPy {result['versions']['numpy']}.", "",
              f"Data lengkap: [{prefix}/calibration.json]({prefix}/calibration.json). "
              "parameters.npz menyimpan semua titik dan valid_mask; terapkan mask sebelum evaluasi ulang. "
              "Titik yang dikecualikan dilingkari oranye pada folder corners.", ""]
    target.write_text("\n".join(lines), encoding="utf-8")
