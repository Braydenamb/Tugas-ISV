# Perbandingan pemrosesan

| Profil | Foto | Titik | Mean (px) | RMS (px) |
|---|---:|---:|---:|---:|
| baseline | 29 | 1418 | 2.328715 | 2.883255 |
| mild | 29 | 1418 | 2.328840 | 2.905960 |

Kedua run memakai foto, hash, dan identitas titik yang sama.

Profil mild menambahkan Gaussian 3x3 sigma 0,8 dan CLAHE clipLimit 1,5 grid 8x8. Ini perbandingan kecocokan pada data kalibrasi, bukan validasi independen atau bukti bahwa posisi sudut lebih akurat.
