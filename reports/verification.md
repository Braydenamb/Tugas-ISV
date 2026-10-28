# Verifikasi penyiapan dan pemrosesan

## Hasil pemrosesan

Kedua profil memakai 29 foto yang sama, 1.418 titik yang sama, dan tiga pengecualian yang sama. Identitas foto, hash sumber, serta valid_mask dibandingkan langsung. Mean dan RMS dihitung ulang secara independen dari parameter NPZ melalui projectPoints.

| Profil | Mean (px) | RMS (px) |
|---|---:|---:|
| baseline | 2.328715 | 2.883255 |
| mild (Gaussian + CLAHE) | 2.328840 | 2.905960 |

Gaussian + CLAHE belum menunjukkan perbaikan pada dataset ini. Karena RMS justru meningkat, baseline dipertahankan sebagai default. Profil tambahan tetap tersedia untuk percobaan yang dicatat. Tidak ada klaim bahwa penurunan error pada data kalibrasi membuktikan ketepatan pada foto independen. Error kedua profil masih lebih tinggi daripada acuan kualitas baik pada materi.

## Pemeriksaan yang selesai

1. Semua 29 foto setelah pemindahan folder mempunyai SHA-256 yang sama dengan foto sebelum pemindahan.
2. Initializer berhasil membuat `.venv` baru dan memasang seluruh dependensi; `--check` berhasil memeriksa lingkungan tersebut.
3. Program berhasil dijalankan dari direktori kerja lain; tidak membutuhkan arsip, lokasi absolut mesin pembuat, atau lingkungan Python lama.
4. Salinan bersih yang hanya berisi berkas calon repo (tanpa `.git`, `archive`, `outputs`, `.venv`, dan cache) berhasil menjalankan `python initialize.py --run`. Lingkungan dibuat dari awal dan semua 29 foto berhasil diproses. Hasil mean/RMS cocok dengan baseline dengan toleransi 0,00001 piksel.
5. Tiga tes terarah lulus: mean berbeda dari RMS; koordinat hasil dua profil kembali ke piksel foto perspektif yang diketahui; foto dengan nama sama tetapi isi berubah tidak memakai kembali koordinat cache.
6. Git mengabaikan lingkungan Python, hasil run, cache, arsip dan laporan otomatis. Foto, inisialisasi, konfigurasi, kode, materi, dan tes termasuk dalam salinan bersih.

Lingkungan uji: Python 3.14.8, OpenCV 5.0.0, NumPy 2.5.4. Dependensi lengkap dapat bervariasi sesuai versi Python/platform; versi aktual dicatat pada setiap calibration.json.
