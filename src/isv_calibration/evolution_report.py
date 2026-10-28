"""Build the same method-evolution content as Markdown and a reviewed A4 PDF."""
from pathlib import Path
from html import escape
import json
import shutil

import numpy as np

from .calibration import ROOT


def _safe(result):
    health = result["distortion_health"]
    return (not health["pole_within_approximate_sensor_extent"]
            and health["nonpositive_or_nonfinite_jacobian_fraction"] == 0)


def build_evolution_report(results_folder):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    folder = Path(results_folder).resolve()
    summary = json.loads((folder / "refinement_summary.json").read_text(encoding="utf-8"))
    history = json.loads((ROOT / "reports/data/method_history.json").read_text(encoding="utf-8"))["stages"]
    reference = summary["reference_methods"]["results"]
    followups = summary["follow_up_results"]
    square_size_mm = summary["square_size_mm"]
    baseline = json.loads((folder / "reference_methods/baseline_reference/calibration.json").read_text(encoding="utf-8"))
    original_best = reference[-1]
    candidates = [{**original_best, "experiment_id": "global100_standard5"}] + followups
    selected = min((r for r in candidates if _safe(r)), key=lambda r: (r["validation_rms_px"], r["validation_mean_px"]))
    selected_folder = folder / selected["experiment_id"]
    if selected["experiment_id"] == "global100_standard5":
        selected_folder = folder / "reference_methods/checker_correlation_two_panels"
    assets = ROOT / "reports/assets"
    assets.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4))
    x = np.arange(len(history))
    bars = ax.bar(x, [r["mean_px"] for r in history], color="#155e75")
    ax.bar_label(bars, fmt="%.3f", padding=3)
    ax.set_xticks(x, [f"{r['id']}\n{r['photos']} foto / {r['points']} titik" for r in history])
    ax.set(ylabel="Mean error (px)", title="Riwayat pengerjaan; jumlah titik dan versi tidak selalu sama")
    ax.margins(y=.15)
    fig.tight_layout()
    fig.savefig(assets / "evolution_history.png", dpi=160)
    plt.close(fig)
    shutil.copy2(folder / "reference_methods/comparison.png", assets / "evolution_panels.png")
    # Compact labels make individual follow-up changes readable in the report.
    fig, ax = plt.subplots(figsize=(10, 4))
    x = np.arange(len(candidates))
    ax.bar(x-.18, [r["training_mean_px"] for r in candidates], .36, label="Mean kalibrasi")
    ax.bar(x+.18, [r["validation_mean_px"] for r in candidates], .36, label="Mean validasi silang")
    ax.set_xticks(x, [f"N{i}" for i in range(len(candidates))])
    ax.set(ylabel="Mean error (px)", title="Metode lanjutan: 29 foto, 1.216 titik dan 579 evaluasi yang sama")
    ax.legend()
    fig.tight_layout()
    fig.savefig(assets / "evolution_followups.png", dpi=160)
    plt.close(fig)
    full_names = ["k1", "k2", "p1", "p2", "k3", "k4", "k5", "k6", "s1", "s2", "s3", "s4", "tau_x", "tau_y"]
    active = list(range(5))
    if selected["lens_model"] == "polynomial5_plus_prism4":
        active += [8, 9, 10, 11]
    elif len(selected["distortion"]) > 5:
        active = list(range(min(12, len(selected["distortion"]))))
    fig, ax = plt.subplots(figsize=(8, 3))
    bars = ax.bar([full_names[i] for i in active], [selected["distortion"][i] for i in active], color="#155e75")
    ax.axhline(0, color="black", lw=.5)
    ax.bar_label(bars, fmt="%.4f", padding=3, fontsize=8)
    ax.margins(y=.2)
    ax.set(ylabel="Koefisien", title="Koefisien aktif varian eksperimen terpilih")
    fig.tight_layout()
    fig.savefig(assets / "evolution_distortion.png", dpi=160)
    plt.close(fig)

    pages = [[] for _ in range(6)]
    def heading(page, text): pages[page].append(("heading", text))
    def text(page, value): pages[page].append(("text", value))
    def table(page, rows, widths): pages[page].append(("table", rows, widths))
    def figure(page, name, width, height, caption): pages[page].append(("figure", name, width, height, caption))
    def code(page, value): pages[page].append(("code", value))
    pages[0].append(("title", "Perkembangan Metode\nKalibrasi Kamera"))
    text(0, "Tugas Mandiri Instrumentasi Sistem Visual | Pertemuan 10")
    heading(0, "1. Tujuan, data, dan batas perbandingan")
    text(0, "Laporan ini mendokumentasikan perubahan metode beserta dampaknya terhadap error. Riwayat yang jumlah titik/versinya berubah dipisahkan dari eksperimen terkontrol yang memakai identitas titik sama. Hasil yang tidak membantu dan hasil numerik yang bermasalah tetap dicatat.")
    table(0, [["Aspek", "Keterangan"], ["Foto", "29 foto asli; 3120 x 4160 piksel"],
              ["Pola dan ukuran", f"8 x 8 kotak; 7 x 7 sudut dalam; sisi {square_size_mm:g} mm sesuai konfigurasi"],
              ["Akuisisi terkonfirmasi", "Kamera dan zoom sama; fokus otomatis; posisi/orientasi kamera berubah"],
              ["Metode dasar", "Target planar Z=0, refinement sudut dan cv2.calibrateCamera sesuai materi hlm. 45-54, 57-60"],
              ["Perluasan", "Pengukuran berbasis citra, model dua panel, resolusi perataan, dan model distorsi tambahan"]], [117,398])
    heading(0, "2. Definisi metrik")
    text(0, "Untuk tiap titik yang dipakai, e = ||p_terukur - p_proyeksi||. Mean = jumlah(e)/M dan RMS = akar[jumlah(e^2)/M], dalam piksel. Nilai balik calibrateCamera adalah RMS; mean dihitung terpisah melalui projectPoints. Contoh cetak hlm. 59 menyebut mean, sedangkan hlm. 60 menjelaskan RMS; laporan ini mempertahankan keduanya.")
    text(0, "Perubahan posisi kamera memang diperlukan untuk menyediakan pose beragam. Fokus otomatis merupakan kemungkinan sumber variasi intrinsik pada sebagian kamera; pengaruhnya pada dataset ini belum diukur. Pengembangan model tetap mengasumsikan satu K/distorsi bersama, sehingga kontrol fokus penting untuk pengambilan ulang.")
    heading(0, "3. Hasil metode dasar saat ini (H3)")
    text(0, f"29 foto, 1.418 titik: mean {baseline['mean_reprojection_error_px']:.6f} px dan RMS {baseline['rms_reprojection_error_px']:.6f} px. Tiga pengamatan ambigu dikecualikan berdasarkan citra: WA0101 (baris 7 kolom 4), WA0089 (7,7), dan WA0094 (6,3). Semua foto tetap dipakai.")
    K0 = np.array(baseline["K"])
    text(0, f"K dasar: fx={K0[0,0]:.5f}, fy={K0[1,1]:.5f}, cx={K0[0,2]:.5f}, cy={K0[1,2]:.5f} piksel; skew=0 dan K33=1. D dasar [k1,k2,p1,p2,k3] = " + ", ".join(f"{v:.6f}" for v in baseline["distortion"]) + ".")

    heading(1, "4. Riwayat pengerjaan: perubahan data dan deteksi")
    table(1, [["Tahap", "Foto", "Titik", "Mean px", "RMS px", "OpenCV"]] +
          [[r["id"], str(r["photos"]), str(r["points"]), f"{r['mean_px']:.4f}", f"{r['rms_px']:.4f}", r["opencv"]] for r in history], [60,55,75,105,105,115])
    for row in history:
        text(1, f"{row['id']} - {row['title']}: {row['change']}")
    figure(1, "evolution_history.png", 500, 205, "Gambar 1. Riwayat hasil. Diagram ini tidak menyatakan hubungan sebab-akibat antarjumlah foto/titik yang berbeda.")
    text(1, "H0-H2 tidak menggunakan kumpulan pengamatan yang sama. H2-H3 juga berbeda lingkungan OpenCV. Mengubah ukuran seragam dari 42 menjadi 44 mm hanya mengubah skala translasi; perubahan ukuran bukan penyebab turunnya error. Perbedaan kecil H2-H3 terkait lingkungan/pengolahan. H3-H4 memakai pengamatan yang sama dan menunjukkan Gaussian+CLAHE tidak membantu: RMS meningkat.")
    text(1, "Snapshot angka, versi, ukuran, alasan perubahan, lokasi artefak lama, dan hash SHA-256 sumber tersedia pada reports/data/method_history.json. Artefak lama dipertahankan di arsip lokal; snapshot disertakan agar riwayat tetap terlihat setelah clone.")

    heading(2, "5. Eksperimen terkontrol: detektor dan bentuk papan")
    text(2, "Garis sudut pada celah tengah dikecualikan secara seragam berdasarkan geometri, tanpa melihat residual: 203 titik sambungan (termasuk satu yang sudah ambigu), serta dua titik ambigu lain di luar sambungan. Tersisa 1.216 identitas titik yang sama pada seluruh varian. Jumlah foto tetap 29. CV berarti validasi silang.")
    table(2, [["ID / detektor / model", "Mean latih", "RMS latih", "Mean CV", "RMS CV"]] +
          [[f"C{i+1}: {r['detector']} / {r['model']}", f"{r['training_mean_px']:.4f}", f"{r['training_rms_px']:.4f}", f"{r['validation_mean_px']:.4f}", f"{r['validation_rms_px']:.4f}"] for i,r in enumerate(reference)], [195,80,80,80,80])
    figure(2, "evolution_panels.png", 500, 230, "Gambar 2. Semua varian memakai 1.216 titik kalibrasi dan 579 titik evaluasi silang yang sama.")
    text(2, "C1 -> C2 mengubah model menjadi dua panel: mean turun sekitar 2,095 -> 0,902 px. C2 -> C4 mengganti pengukuran sudut menjadi korelasi empat kuadran: sekitar 0,902 -> 0,780 px. C1 -> C3 menunjukkan korelasi saja memberi perbaikan jauh lebih kecil. Model dua panel merupakan perubahan dominan pada pengujian ini.")
    text(2, "Dua panel berbagi K/distorsi, tetapi memiliki dua pose per foto: 58 pose dari 29 foto. Tambahan enam parameter pose per foto dapat menurunkan error latih; karena itu hasil juga dibandingkan melalui validasi silang. Ini pengembangan atas contoh satu papan datar dalam materi, dan tidak diganti namanya seolah prosedur identik.")

    heading(3, "6. Langkah lanjutan: resolusi dan model distorsi")
    table(3, [["ID / perubahan", "Mean latih", "RMS latih", "Mean CV", "RMS CV", "Screen"]] +
          [[f"N{i}: {r['experiment_id']}", f"{r['training_mean_px']:.4f}", f"{r['training_rms_px']:.4f}", f"{r['validation_mean_px']:.4f}", f"{r['validation_rms_px']:.4f}", "Lolos*" if _safe(r) else "Tolak"] for i,r in enumerate(candidates)], [170,69,69,69,69,69])
    figure(3, "evolution_followups.png", 500, 200, "Gambar 3. N0 adalah korelasi global 100 piksel/kotak dan lima koefisien. Seluruh eksperimen memakai titik serta pembagian CV yang sama.")
    text(3, "N1 menaikkan resolusi menjadi 200 piksel/kotak. N2-N3 memakai homografi awal per panel. N4 mengunci k3=0. N5 memakai rational delapan koefisien. N6 menambah empat suku thin-prism tanpa denominator rational (sembilan koefisien aktif). N7 menggabungkan rational dan prism (12 aktif). N8 menggabungkan resolusi 200 dengan thin-prism sembilan koefisien.")
    text(3, "*Lolos berarti hanya lolos pemeriksaan numerik terbatas: tidak ditemukan pole denominator pada area radius sensor perkiraan dan tidak ada Jacobian nonpositif pada grid 31 x 31. Ini bukan bukti invertibilitas global atau akurasi di seluruh sensor. N4 menunjukkan pembalikan pada sebagian grid perkiraan; N7 mempunyai pole positif sekitar r=0,465 dan tidak direkomendasikan untuk seluruh gambar meski error latih turun.")
    text(3, "Resolusi lebih tinggi memberi perbaikan kecil, sedangkan homografi per panel tidak menunjukkan keuntungan konsisten. Menambah koefisien rational saja hampir tidak membantu. Hasil negatif tersebut tetap disertakan agar keputusan tidak hanya didasarkan pada percobaan terbaik.")

    heading(4, "7. Varian eksperimen paling menjanjikan")
    text(4, f"Terpilih pada uji internal: {selected['experiment_id']}. Pemilihan berdasarkan RMS CV terendah di antara varian yang lolos screen numerik. Metode dasar tetap tersedia dan tidak diganti otomatis. Hasil: mean {selected['training_mean_px']:.6f} px; RMS {selected['training_rms_px']:.6f} px; mean CV {selected['validation_mean_px']:.6f} px; RMS CV {selected['validation_rms_px']:.6f} px.")
    code(4, "K eksperimen (piksel):\n" + "\n".join("["+" ".join(f"{v:12.5f}" for v in row)+"]" for row in selected["K"]))
    table(4, [["Koefisien aktif", "Nilai"]] + [[full_names[i], f"{selected['distortion'][i]:.9f}"] for i in active], [180,335])
    figure(4, "evolution_distortion.png", 490, 170, "Gambar 4. Koefisien aktif varian terpilih. Tinggi batang tidak langsung menyatakan perpindahan piksel.")
    text(4, "Thin-prism menambahkan suku geometris s1-s4; keberhasilan fit tidak mengidentifikasi penyebab fisik secara pasti. Dalam format OpenCV, koefisien k4-k6 tetap nol pada varian prism tanpa rational. Semua nilai K berlaku pada ukuran gambar dan asumsi kamera bersama yang digunakan di sini.")

    heading(5, "8. Validasi, keterbatasan, dan keputusan berikutnya")
    text(5, "Lima bagian CV menahan seluruh foto dari estimasi K/distorsi. Pada foto tertahan, pose diperkirakan dari titik jangkar berselang-seling; error dihitung pada 579 titik lain yang tidak dipakai untuk pose. Rencana menyimpan foto training/tertahan, indeks titik, K, distorsi, dan pose sehingga proyeksi dapat dihitung ulang. Tidak ada foto/titik yang dihapus menggunakan ambang residual.")
    text(5, "CV yang sama telah digunakan untuk mencoba dan memilih beberapa metode. Karena itu, hasil merupakan validasi internal yang dapat optimistis setelah pemilihan metode; belum menjadi hasil pada test set baru. Pemeriksaan titik sintetis dan Jacobian hanya memeriksa bagian tertentu dari pengolahan, bukan ketepatan pengukuran dimensi nyata.")
    text(5, "Menurut acuan materi hlm. 53, error <0,25 px sangat bagus, <0,50 px dapat diterima, dan >1 px perlu kalibrasi ulang. Mean sekitar 0,739 px masih belum memenuhi acuan <0,5 px. Melaporkan RMS sekitar 0,996 sebagai keberhasilan hanya karena melewati angka 1 akan menutupi keterbatasan yang masih ada.")
    text(5, "Prioritas berikutnya: (1) kunci fokus, kamera/lensa dan zoom; variasikan pose sambil menjaga gambar tajam. (2) Gunakan pola yang rata-kaku, petak seragam, dan pencahayaan tanpa pantulan. (3) Ukur rentang beberapa petak untuk memeriksa ukuran dan keseragaman aktual. (4) Ambil foto baru dan sisihkan sebagian sebagai test set yang tidak dipakai memilih metode. Perubahan fokus akibat autofocus merupakan kemungkinan, bukan penyebab tunggal yang sudah dibuktikan.")
    text(5, "Metode lanjutan seperti estimasi geometri target/object-releasing dapat dipertimbangkan setelah ukuran acuan dan identitas titik fisik antar-foto diketahui. Pada papan simetris, urutan sudut dapat berputar; jangan menganggap identitas fisik semua titik otomatis konsisten atau mengubah koordinat objek hanya untuk mengecilkan error.")
    heading(5, "9. Reproduksi dan referensi")
    code(5, "python initialize.py --experiment refinement\n# Setelah dependensi tersedia:\npython initialize.py --skip-install --experiment refinement\n# Bangun ulang laporan dari hasil tersimpan:\npython tools/build_evolution_report.py --results outputs/<run>")
    text(5, f"Ukuran {square_size_mm:g} mm dan orientasi panel ada pada config/. Catatan akuisisi ada pada config/acquisition.json. Tiap kandidat menyimpan parameters.npz, residual tiap titik dan validation_plan.json. Terapkan view_photo_indices serta view_masks saat memasangkan pose dengan panel/foto. Baseline perkuliahan tetap menjadi konfigurasi utama.")
    text(5, "[1] Yakub Fahim Luckyarno. Optika Geometri Kamera & Kalibrasi Sensorik, Pertemuan 10, 25 Oktober 2026, hlm. 45-54, 57-60, 65. [2] Dokumentasi OpenCV calibrateCamera, projectPoints, matchTemplate dan opsi model distorsi. [3] Artefak eksperimen dan snapshot riwayat yang tersimpan dalam proyek. Informasi fokus otomatis berasal dari konfirmasi pengguna.")

    # The same blocks supply both output formats, avoiding divergent report numbers.
    markdown = []
    for number, blocks in enumerate(pages):
        if number:
            markdown += ["", "---", ""]
        for block in blocks:
            kind = block[0]
            if kind == "title": markdown += ["# " + block[1].replace("\n", " "), ""]
            elif kind == "heading": markdown += ["## " + block[1], ""]
            elif kind == "text": markdown += [block[1], ""]
            elif kind == "code": markdown += ["```text", block[1], "```", ""]
            elif kind == "figure": markdown += [f"![{block[4]}](assets/{block[1]})", ""]
            elif kind == "table":
                rows = block[1]
                markdown += ["| " + " | ".join(str(x).replace("\n", " ") for x in rows[0]) + " |", "|" + "---|"*len(rows[0])]
                markdown += ["| " + " | ".join(str(x).replace("\n", " ") for x in row) + " |" for row in rows[1:]] + [""]
    (ROOT / "reports/evolution.md").write_text("\n".join(markdown), encoding="utf-8")
    import hashlib
    source_record = {"history": history, "reference_methods": reference, "follow_up_results": followups,
                     "selected": selected, "selection_rule": "lowest internal CV RMS among models passing limited numerical screen",
                     "versions": summary["reference_methods"]["versions"], "acquisition": summary["acquisition"],
                     "source_summary_sha256": hashlib.sha256((folder / "refinement_summary.json").read_bytes()).hexdigest()}
    (ROOT / "reports/data/evolution_summary.json").write_text(json.dumps(source_record, indent=2), encoding="utf-8")
    pdf = ROOT / "reports/Laporan_Perkembangan_Kalibrasi.pdf"
    _render_pdf(pages, assets, pdf, square_size_mm)
    return pdf


def _render_pdf(pages, assets, target, square_size_mm=44):
    import matplotlib
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image, Preformatted, PageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    font_dir = Path(matplotlib.get_data_path()) / "fonts/ttf"
    pdfmetrics.registerFont(TTFont("EvolutionBody", str(font_dir / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("EvolutionBold", str(font_dir / "DejaVuSans-Bold.ttf")))
    body = ParagraphStyle("EvolutionText", fontName="EvolutionBody", fontSize=9, leading=12.8, spaceAfter=7)
    small = ParagraphStyle("EvolutionSmall", parent=body, fontSize=7.3, leading=9.9, spaceAfter=0)
    heading = ParagraphStyle("EvolutionHeading", fontName="EvolutionBold", fontSize=12, leading=16, spaceBefore=8, spaceAfter=8, textColor=colors.HexColor("#123e5a"))
    title = ParagraphStyle("EvolutionTitle", parent=heading, fontSize=19, leading=24)
    mono = ParagraphStyle("EvolutionCode", fontName="Courier", fontSize=8.4, leading=12, spaceAfter=8)
    story = []
    for page_number, blocks in enumerate(pages):
        if page_number:
            story.append(PageBreak())
        for block in blocks:
            kind = block[0]
            if kind in ("title", "heading", "text"):
                style = title if kind == "title" else heading if kind == "heading" else body
                story.append(Paragraph(escape(block[1]).replace("\n", "<br/>"), style))
            elif kind == "code": story.append(Preformatted(block[1], mono))
            elif kind == "figure":
                story.append(Image(str(assets / block[1]), width=block[2], height=block[3]))
                story.append(Paragraph(escape(block[4]), small))
                story.append(Spacer(1, 7))
            elif kind == "table":
                rows = [[Paragraph(escape(str(cell)).replace("\n", "<br/>"), small) for cell in row] for row in block[1]]
                table = Table(rows, colWidths=block[2], repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e8f0f5")),
                                           ("VALIGN", (0,0), (-1,-1), "TOP"),
                                           ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
                                           ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
                                           ("LINEBELOW", (0,0), (-1,-1), .25, colors.HexColor("#cdd9e0"))]))
                story.extend([table, Spacer(1, 8)])
    def footer(canvas, doc):
        width, _ = A4
        canvas.setFont("EvolutionBody", 7)
        canvas.setFillColor(colors.HexColor("#526572"))
        canvas.drawString(40, 24, f"ISV | Riwayat metode dan validasi | Kotak {square_size_mm:g} mm")
        canvas.drawRightString(width-40, 24, str(doc.page))
    SimpleDocTemplate(str(target), pagesize=A4, leftMargin=40, rightMargin=40, topMargin=32,
                      bottomMargin=43, title="Perkembangan Metode Kalibrasi Kamera", author="").build(story, onFirstPage=footer, onLaterPages=footer)
