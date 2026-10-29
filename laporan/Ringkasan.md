# Hasil Tugas Mandiri ISV

Jalankan `python mulai.py`, lalu buka `laporan/Laporan.pdf`.

| Tahap | Perubahan | Titik | Mean px | RMS px | Mean CV |
|---|---|---:|---:|---:|---:|
| 1 | Deteksi dan audit sudut | 1418 | 2.3287 | 2.8833 | 2.4835 |
| 2 | Abaikan garis sambungan | 1216 | 2.0948 | 2.4491 | 2.1351 |
| 3 | Model dua panel | 1216 | 0.9024 | 1.2762 | 0.9680 |
| 4 | Korelasi pola | 1216 | 0.7803 | 1.0483 | 0.7883 |
| 5 | Resolusi lebih tinggi | 1216 | 0.7737 | 1.0507 | 0.7757 |
| 6 | Model distorsi akhir | 1216 | 0.7391 | 0.9961 | 0.7364 |

Tahap 2-6 memakai 1.216 titik yang sama. Mean dan RMS berbeda; hasil masih belum memenuhi acuan <0,5 px.

Visual tahapan dan pembesaran error ada di halaman 2-3 PDF serta `audit/06_hasil_akhir/Visual_Proses.png` dan `Visual_Detail.png`.

Semua audit ikut Git pada folder `audit/`. Riwayat lama ada dalam `audit/Riwayat_Audit.zip`.

Kamera dan zoom sama, fokus otomatis, pose bervariasi menurut keterangan pengguna. Kontribusi autofocus belum diukur.
