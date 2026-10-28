# Tugas Mandiri ISV - Kalibrasi Kamera

## Berkas utama terbaru

- Laporan: `output/pdf/Laporan_Tugas_Mandiri_Kalibrasi.pdf`.
- Program yang dijalankan: `kalibrasi_final.py`.
- Hasil perhitungan: `hasil_final/`.
- Ukuran kotak: **4,4 x 4,4 cm = 44 x 44 mm**.
- Papan: 8 x 8 kotak, sehingga 7 x 7 sudut dalam.
- Foto: seluruh 29 foto dari kedua subfolder `../Photo`.
- Titik digunakan: 1.418; tiga titik ambigu dijelaskan di `titik_ambigu.json`.

## Menjalankan

Buka terminal di folder Project. Jika lingkungan Python sudah tersedia:

```bash
source .venv/bin/activate
python kalibrasi_final.py
```

Jika membuat lingkungan baru:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python kalibrasi_final.py
```

Ukuran 44 mm sudah menjadi default. Untuk menuliskannya secara eksplisit, gunakan `python kalibrasi_final.py --square-mm 44`.

Skrip telah dijalankan pada lingkungan Python proyek dengan OpenCV 5.0.0. Versi paket/platform dapat menyebabkan selisih numerik kecil. Hasil final aktual disimpan di JSON, bukan hanya disalin dari percobaan lama.

## Metode dan batas hasil

Alur kalibrasi mengikuti materi Pertemuan 10 halaman 45-52 dan 57-60: koordinat objek pada Z=0, pasangan titik citra, refinement sudut, dan `calibrateCamera`. `projectPoints` dipakai untuk menghitung mean jarak Euclidean terpisah dari RMS keluaran OpenCV. Plot distorsi memenuhi keluaran yang diminta pada halaman 65.

Deteksi sudut untuk dataset ini memakai pengukuran ulang berbasis respons sudut lokal melalui `deteksi_audit.py`, dengan inisialisasi tersimpan di `data/inisialisasi_sudut.npz`. Inisialisasi hanya menentukan wilayah pencarian; koordinat akhir diukur dari foto asli. Ini merupakan penyesuaian tambahan terhadap contoh deteksi langsung pada materi, bukan salinan persis contoh tersebut. Tiga titik ambigu dikecualikan berdasarkan tinjauan citra. Semua 29 foto tetap digunakan.

Program final khusus dataset yang sudah diaudit. Untuk foto baru, diperlukan deteksi awal dan audit yang sesuai; menambahkan foto baru langsung belum didukung.

Error masih di atas acuan kualitas baik pada materi. Laporan menyatakan keterbatasan ini. K berlaku untuk ukuran gambar 3120 x 4160 dan konfigurasi kamera yang sama. Kesamaan kamera, fokus, dan zoom tidak dapat dibuktikan hanya dari resolusi. Ukuran kotak tidak membuktikan panjang fokus fisik dalam mm.

## Isi hasil_final

- `hasil_kalibrasi.json`: K, distorsi, mean/RMS, ukuran petak, hasil tiap foto dan titik yang dikecualikan.
- `parameter_kalibrasi.npz`: titik 2D/3D, K, distorsi, pose, nama foto, ukuran gambar dan valid_mask. Terapkan valid_mask saat memproses titik: tiga titik bernilai False tidak dipakai kalibrasi.
- `koefisien_distorsi.png`, `error_per_foto.png`, `residual.png`: grafik hasil.
- `error_per_foto.csv`: angka hasil tiap foto.
- `deteksi/`: bukti penanda sudut. Titik yang dikecualikan dilingkari oranye.
- `audit/`: rincian pengukuran sudut tiap foto.
- `sebelum_sesudah.jpg`: contoh koreksi distorsi, bukan bukti akurasi independen.

## Riwayat percobaan

`hasil`, `hasil_semua_foto`, `hasil_audit` dan laporan lama dipertahankan sebagai riwayat percobaan dengan ukuran 42 mm serta versi pengolahan sebelumnya. Jangan memakai angka lama sebagai hasil final 44 mm. Nama subfolder Photo/Dipakai dan Photo/Belum_Dipakai merujuk percobaan awal; keduanya dibaca dalam program final. Jangan hapus `data`, `deteksi_audit.py`, atau `titik_ambigu.json` yang dibutuhkan program final.

Referensi utama: materi kuliah yang diberikan, `c0e37ba42e3421cae2a35909c790e054.pdf`, halaman 45-54, 57-60 dan 65.
