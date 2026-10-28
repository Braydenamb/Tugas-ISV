# Kalibrasi Kamera - Tugas Mandiri ISV

Kalibrasi papan catur mengikuti materi Pertemuan 10: pasangan titik objek/citra,
refinement sudut, `calibrateCamera`, plot distorsi, serta mean dan RMS error.
Dataset bawaan memiliki **29 foto**, pola **7 x 7 sudut dalam** (8 x 8 kotak),
dan sisi kotak **44 mm**.

Laporan lengkap perubahan metode tersedia di
[reports/evolution.md](reports/evolution.md) dan
[PDF perkembangan](reports/Laporan_Perkembangan_Kalibrasi.pdf).
Laporan memisahkan riwayat dengan jumlah titik/versi berbeda dari eksperimen
terkontrol, serta mencatat hasil yang tidak membantu atau ditolak.

## Mulai setelah clone/download

Pasang Python **3.10 atau lebih baru**, lalu buka terminal di folder repo:

```bash
python initialize.py --run
```

Pada Linux/macOS yang memakai nama `python3`, gunakan:

```bash
python3 initialize.py --run
```

Initializer membuat `.venv`, memasang dependensi, memeriksa dataset dan versi
pustaka, lalu menjalankan kalibrasi. Internet dibutuhkan saat pemasangan pertama.
Program tidak memakai jalur absolut komputer pembuat dan dapat dipanggil dari
folder kerja lain dengan memberikan lokasi script lengkap.

Untuk memeriksa instalasi tanpa mengubah proyek:

```bash
python initialize.py --check
```

Untuk menjalankan lagi tanpa pemasangan dependensi:

```bash
python initialize.py --skip-install --run
```

## Pemrosesan tambahan dan perbandingan

```bash
python initialize.py --skip-install --compare
```

Jika `.venv` sudah aktif, perintah langsungnya:

```bash
python run.py
python run.py --preprocessing mild
python run.py --compare
python run.py --photos /lokasi/foto-lain
```

- **baseline**: pengukuran ulang sudut berbasis citra hasil audit, tanpa Gaussian
  3x3 tambahan atau CLAHE. Ini pilihan utama.
- **mild**: Gaussian 3x3, sigma 0,8, lalu CLAHE clipLimit 1,5 dan grid 8x8 untuk
  pencarian sudut. Refinement akhir tidak memakai kontras CLAHE.

Keduanya mengembalikan titik ke koordinat piksel foto asli sebelum kalibrasi.
Homografi hanya membantu pencarian, bukan mengganti titik dengan proyeksi ideal.
Program tidak menggeser titik agar sesuai model atau membuang titik berdasarkan
error. Tiga titik ambigu dari dataset bawaan memiliki alasan visual tertulis
di `config/excluded_points.json` dan berlaku sama pada kedua profil.

Pada uji 29 foto/1.418 titik, baseline memberi mean sekitar **2,329 px**, RMS
**2,883 px**. Tambahan mild memberi mean sekitar **2,329 px**, RMS **2,906 px**;
belum menunjukkan perbaikan, sehingga tidak dijadikan default. Ini kecocokan
pada data kalibrasi, bukan validasi pada foto independen. CLAHE/blur tidak bisa
meratakan papan secara fisik atau menghilangkan celah sambungan.

## Metode alternatif: korelasi sudut dan dua panel

Jalankan eksperimen yang menggunakan bentuk fisik papan lipat:

```bash
python initialize.py --skip-install --experiment panels
```

Untuk instalasi baru, hilangkan `--skip-install` agar dependensi dipasang dulu.
Jika `.venv` aktif, perintah langsungnya `python run.py --experiment panels`.

Eksperimen membandingkan empat kombinasi: deteksi hasil audit/korelasi pola empat
kuadran, masing-masing dengan model satu bidang/dua panel. Model dua panel
memakai satu K dan distorsi bersama, serta dua pose per foto. Semua 29 foto
dipertahankan; garis titik pada celah tengah dikecualikan secara seragam dari
semua kombinasi, sehingga perbandingan memakai 1.216 titik yang sama.

Validasi silang lima bagian menahan foto dari estimasi intrinsik. Pada foto
tertahan, pose dihitung dari titik jangkar, lalu error dinilai pada titik lain.
Model dua panel memiliki parameter lebih banyak; penurunan error latih saja
tidak cukup. Hasilnya merupakan pengembangan atas asumsi satu papan datar pada
materi dan harus dijelaskan sebagai eksperimen, bukan prosedur identik.

Eksperimen khusus dataset 7x7 yang orientasi sambungannya tercatat pada
`config/board_panels.json`. Hash foto diverifikasi sebelum konfigurasi panel
diterapkan. Dataset lain perlu pemeriksaan orientasi dan konfigurasi yang sesuai.

Baca `reports/alternatives.md` setelah run, atau [ringkasan penelitian metode](reports/method_study.md).
Baseline perkuliahan tetap menjadi default; eksperimen tidak menggantinya otomatis.

## Pengujian lanjutan dan laporan otomatis

```bash
python initialize.py --skip-install --experiment refinement
```

Instalasi pertama memakai `python initialize.py --experiment refinement`
(tanpa `--skip-install`). Ini menjalankan ulang metode referensi, menguji
resolusi perataan/homografi panel dan model distorsi alternatif pada identitas
titik yang sama, memeriksa singularitas serta Jacobian, lalu memperbarui
laporan Markdown dan PDF secara otomatis.

Rincian tiap run berada di `reports/refinement.md`; riwayat lengkap pada
`reports/evolution.md` dan PDF perkembangan. Untuk membangun ulang laporan
tanpa mengulang pengukuran/kalibrasi:

```bash
python tools/build_evolution_report.py --results outputs/<folder-run>
```

Catatan akuisisi pengguna: kamera/zoom sama, fokus otomatis, pose bervariasi.
Posisi kamera yang berubah memang diperlukan. Fokus otomatis berpotensi
mengubah intrinsik, tetapi kontribusinya pada error ini belum diukur.
Sumber kemungkinan tersebut dicatat di `config/acquisition.json`.

Varian 200 piksel/kotak + thin-prism tanpa rational menghasilkan mean sekitar
0,739 px, RMS 0,996 px dan mean CV 0,736 px pada pengujian internal. Ini belum
memenuhi acuan <0,5 px. Model rational+prism yang mempunyai error latih kecil
ditolak untuk rekomendasi seluruh gambar karena pole/pembalikan pemetaan pada
area uji perkiraan. Tidak ada klaim akurasi pada data independen.

## Struktur folder

```text
initialize.py              penyiapan untuk pemakai baru (Windows/Linux/macOS)
run.py                     satu pintu menjalankan kalibrasi
requirements.txt           dependensi Python
config/                    ukuran papan, pilihan profil, dan titik ambigu
src/isv_calibration/        pengukuran sudut, kalibrasi, grafik, laporan
data/photos/               29 foto asli
data/initial_corners.npz   inisialisasi dataset yang telah diaudit
data/dataset_manifest.json hash foto dan kelompok percobaan sebelumnya
references/Pertemuan_10.pdf materi acuan
reports/                   laporan, perbandingan, PDF rekaman awal
tests/                     pengujian koordinat dan definisi error
outputs/                   hasil setiap run (diabaikan Git)
archive/                   percobaan lama/berkas lokal (diabaikan Git)
```

Struktur lama disimpan utuh di `archive/legacy_project`. Program sekarang tidak
membutuhkan folder arsip atau lingkungan Python lama.

## Hasil yang dibaca

Setelah run, buka **`reports/latest.md`**. Folder run baru di `outputs/` berisi:

- `calibration.json`: K, distorsi, mean/RMS, versi pustaka, hash input, dan alasan pengecualian.
- `parameters.npz`: titik asli, parameter, pose, dan `valid_mask`. Terapkan mask saat evaluasi ulang.
- `distortion.png`, `errors_per_photo.png`, `residuals.png`: grafik hasil.
- `errors_per_photo.csv`, `detection.csv`: hasil dan status setiap foto.
- `corners/`: bukti penanda; titik ambigu dilingkari oranye.
- `preprocessing/original_vs_detection.png`: kiri grayscale asli, kanan citra untuk deteksi.
- `audit/`: respons sudut, refinement, dan catatan pengukuran tiap foto.
- `report.md`: laporan yang mengikuti hasil run tersebut.

Perbandingan menambahkan `comparison.json` dan `comparison.md`. Run selalu
memakai folder baru. Folder hasil yang tidak kosong tidak ditimpa.

## Mengubah papan atau dataset

Edit `config/calibration.json`. `inner_corners` berarti jumlah **sudut dalam**,
bukan jumlah kotak. Ukuran kotak memakai mm. Default minimum foto 12 mengikuti
tugas. Foto harus memakai resolusi dan konfigurasi kamera yang konsisten.

Jika hash foto berubah atau pola berbeda, koordinat cache serta pengecualian
lama tidak digunakan. Program mencoba deteksi otomatis dan mencatat kegagalan.
Tidak semua dataset baru dijamin langsung berhasil; periksa hasil penandaan.

## Acuan dan batas kualitas

Lihat `references/Pertemuan_10.pdf`, hlm. 45-54, 57-60, dan 65. Pengukuran ulang
dan profil mild merupakan penyesuaian deteksi yang dijelaskan di laporan;
kalibrasi utamanya tetap menggunakan model papan datar/OpenCV.

Keluaran pertama `calibrateCamera` adalah **RMS**, meskipun contoh cetak pada
hlm. 59 menyebut mean. Karena itu program menghitung mean jarak Euclidean
secara terpisah dengan `projectPoints` dan melaporkan keduanya.

Error saat ini masih di atas acuan kualitas baik pada materi. Hindari klaim
kalibrasi presisi. Pertimbangkan papan datar-kaku, pencahayaan tanpa pantulan,
dan konfigurasi kamera tetap untuk pengambilan ulang.

## Pengujian

Dengan lingkungan `.venv` aktif:

```bash
python -m unittest discover -s tests -v
```

Tes memeriksa pengembalian koordinat dari perspektif pada citra sintetis dengan
geometri diketahui, membedakan mean jarak dari RMS, dan memastikan perubahan
isi foto tidak memakai ulang koordinat cache. Keberhasilan tes tidak
membuktikan kualitas target papan fisik.

Rincian uji pemasangan dan hasil perbandingan tersedia di [reports/verification.md](reports/verification.md).

Referensi pustaka: [OpenCV camera calibration](https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html) dan [OpenCV CLAHE](https://docs.opencv.org/4.x/d5/daf/tutorial_py_histogram_equalization.html).

## Git

`.gitignore` mengecualikan `.venv`, cache, hasil run, arsip, berkas lokal editor,
dan kredensial. Foto sumber, inisialisasi, konfigurasi, materi, kode, dan tes
disertakan agar proyek dapat dijalankan setelah clone. Tidak ada proses publish
atau push yang dijalankan oleh initializer.
