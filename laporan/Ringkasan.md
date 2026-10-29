# Kalibrasi Kamera - Ringkasan

Laporan PDF memuat lima halaman visual: alur, lokalisasi, galat, hasil, dan pemilihan metode.

| Tahap | Modifikasi | Mean px | RMS px | Mean CV |
|---|---|---:|---:|---:|
| T1 | Deteksi dan audit sudut | 2.3287 | 2.8833 | 2.4835 |
| T2 | Abaikan garis sambungan | 2.0948 | 2.4491 | 2.1351 |
| T3 | Model dua panel | 0.9024 | 1.2762 | 0.9680 |
| T4 | Korelasi pola | 0.7803 | 1.0483 | 0.7883 |
| T5 | Resolusi lebih tinggi | 0.7737 | 1.0507 | 0.7757 |
| T6 | Model distorsi akhir | 0.7391 | 0.9961 | 0.7364 |

Mean akhir belum memenuhi acuan <0,50 px. Validasi masih internal.

29 foto dinamai Kalibrasi_01.jpg sampai Kalibrasi_29.jpg. Pemetaan nama asli dan hash: data/Identitas_Foto.csv.

Jalankan python mulai.py. Foto, audit, pemetaan nama, dan laporan tidak di-ignore Git.
