# Hasil kalibrasi kamera

Profil: **baseline**. Ukuran kotak: **44 mm**. Foto dipakai: **29/29**. Titik dipakai: **1418**.

## Metode

Acuan: [materi Pertemuan 10](../../../references/Pertemuan_10.pdf), hlm. 45-54, 57-60 dan 65. Objek dimodelkan pada Z=0 dengan jarak antarsudut sesuai ukuran kotak. Kalibrasi menggunakan pasangan titik objek/citra dan cv2.calibrateCamera; projectPoints digunakan untuk menghitung error.

Pemrosesan tambahan membantu pengukuran sudut dan dijelaskan sebagai penyesuaian atas contoh materi. Inisialisasi dataset hanya dipakai bila hash foto cocok. Foto lain dideteksi melalui findChessboardCorners atau findChessboardCornersSB. Homografi hanya menentukan wilayah pencarian; koordinat akhir berasal dari respons sudut citra, dikembalikan ke piksel foto asli, dan diperhalus subpiksel. Tidak ada titik digeser ke proyeksi model atau dibuang menggunakan ambang error kalibrasi.

Profil baseline memakai tahap pengukuran hasil audit sebelumnya. Profil mild menambahkan Gaussian 3x3 (sigma 0,8) dan CLAHE (clipLimit 1,5; grid 8x8) untuk pencarian. Refinement akhir memakai intensitas tanpa CLAHE. Keduanya tetap memakai koordinat dan ukuran foto asli.

## Matriks intrinsik K (piksel)

```text
[  3101.135147      0.000000   1528.363273]
[     0.000000   3104.634097   2161.054581]
[     0.000000      0.000000      1.000000]
```

## Koefisien distorsi

| Koefisien | Nilai |
|---|---:|
| k1 | 0.292031877 |
| k2 | -1.800878608 |
| p1 | 0.010743364 |
| p2 | -0.006656404 |
| k3 | 3.054640874 |

![Koefisien distorsi](./distortion.png)

## Error reproyeksi

- Mean: **2.328715 piksel**.
- RMS: **2.883255 piksel**.

Mean = rata-rata jarak Euclidean pengamatan terhadap proyeksi. RMS = akar rata-rata kuadrat jarak tersebut. Nilai balik calibrateCamera adalah RMS; keduanya dilaporkan terpisah karena istilah pada contoh materi hlm. 59-60 tidak konsisten.

![Error per foto](./errors_per_photo.png)

| Foto | Titik | Mean (px) | RMS (px) |
|---|---:|---:|---:|
| IMG-20261026-WA0046.jpg | 49 | 1.9629 | 2.2900 |
| IMG-20261026-WA0047.jpg | 49 | 2.5921 | 3.5271 |
| IMG-20261026-WA0074.jpg | 49 | 1.7821 | 2.3300 |
| IMG-20261026-WA0076.jpg | 49 | 1.9395 | 2.5803 |
| IMG-20261026-WA0079.jpg | 49 | 2.2031 | 2.4340 |
| IMG-20261026-WA0080.jpg | 49 | 1.7727 | 2.0706 |
| IMG-20261026-WA0081.jpg | 49 | 2.2536 | 2.5897 |
| IMG-20261026-WA0082.jpg | 49 | 2.8823 | 3.4008 |
| IMG-20261026-WA0083.jpg | 49 | 2.2609 | 2.6371 |
| IMG-20261026-WA0084.jpg | 49 | 2.1512 | 2.3837 |
| IMG-20261026-WA0085.jpg | 49 | 2.4774 | 2.8474 |
| IMG-20261026-WA0086.jpg | 49 | 2.9268 | 4.1427 |
| IMG-20261026-WA0087.jpg | 49 | 2.9755 | 4.0689 |
| IMG-20261026-WA0089.jpg | 48 | 2.5096 | 2.9640 |
| IMG-20261026-WA0090.jpg | 49 | 1.7293 | 1.9681 |
| IMG-20261026-WA0091.jpg | 49 | 2.0158 | 2.4586 |
| IMG-20261026-WA0092.jpg | 49 | 1.9643 | 2.2494 |
| IMG-20261026-WA0093.jpg | 49 | 2.2953 | 2.6011 |
| IMG-20261026-WA0094.jpg | 48 | 1.8268 | 2.0297 |
| IMG-20261026-WA0095.jpg | 49 | 2.9761 | 3.3092 |
| IMG-20261026-WA0096.jpg | 49 | 2.3404 | 3.2420 |
| IMG-20261026-WA0097.jpg | 49 | 1.9486 | 2.3581 |
| IMG-20261026-WA0098.jpg | 49 | 2.9953 | 3.5462 |
| IMG-20261026-WA0099.jpg | 49 | 2.2071 | 2.4635 |
| IMG-20261026-WA0101.jpg | 48 | 2.0629 | 3.0371 |
| IMG-20261026-WA0102.jpg | 49 | 3.2040 | 3.5904 |
| IMG-20261026-WA0103.jpg | 49 | 3.6062 | 4.0346 |
| IMG-20261026-WA0104.jpg | 49 | 1.8493 | 2.1857 |
| IMG-20261026-WA0105.jpg | 49 | 1.8097 | 2.1960 |

## Pengamatan yang dikecualikan

- IMG-20261026-WA0089.jpg, baris 7 kolom 7: Pantulan kuat menutupi batas warna; penanda tertarik pada tekstur kayu dan posisi sudut tidak dapat ditetapkan dengan yakin.
- IMG-20261026-WA0094.jpg, baris 6 kolom 3: Pantulan dan tekstur mengaburkan pertemuan empat kotak; lokalisasi sudut tidak dapat dipastikan dari gambar.
- IMG-20261026-WA0101.jpg, baris 7 kolom 4: Penanda jatuh pada tekstur/pantulan di sisi celah papan; persilangan tunggal empat kotak tidak dapat ditetapkan dengan yakin dari gambar.

## Batas interpretasi

Materi hlm. 53 menggunakan acuan <0,25 px sangat bagus, <0,50 px dapat diterima dan >1 px perlu kalibrasi ulang. Ini acuan kuliah, bukan ambang universal untuk semua resolusi/kamera. Error lebih kecil pada data kalibrasi tidak membuktikan akurasi pada data baru. Sambungan, ketidakrataan papan, pantulan dan ketidakseragaman kotak tidak dapat diperbaiki secara fisik melalui CLAHE atau blur. Pengambilan ulang dengan papan datar-kaku dan konfigurasi kamera tetap masih diperlukan bila target akurasi belum tercapai.

Lingkungan: Python 3.14.8, OpenCV 5.0.0, NumPy 2.5.4.

Data lengkap: [./calibration.json](./calibration.json). parameters.npz menyimpan semua titik dan valid_mask; terapkan mask sebelum evaluasi ulang. Titik yang dikecualikan dilingkari oranye pada folder corners.
