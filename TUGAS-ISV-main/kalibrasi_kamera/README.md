# Laporan Tugas Praktikum Mandiri — Kalibrasi Kamera (Papan Catur)

## Setup
- Kamera: smartphone, citra 960×1280 px (portrait)
- Papan catur lipat 8×8 kotak → **7×7 sudut dalam** (49 titik/citra). Ukuran kotak diasumsikan **25.0 mm** (hanya memengaruhi tvecs, tidak memengaruhi K, D, maupun error)
- Foto: 29 → terdeteksi 26 → dipakai 25 (outlier error > 1,5 px dibuang: papan_06.jpg)
- Deteksi (`detector.py`): `findChessboardCorners/SB` multi-skala; bila gagal (garis lipatan), cari sebagian kisi lalu tentukan posisinya di papan 8×8 dengan pencocokan pola terang/gelap + validasi homografi. Semua sudut diperhalus `cornerSubPix`.
- Kalibrasi: `cv2.calibrateCamera` (Zhang), model D = [k1,k2,p1,p2,k3]

## Hasil
Matriks intrinsik K:

```
[[   954.11  0.00    471.13]
 [  0.00    954.89    663.80]
 [  0.00     0.00     1.00]]
```
fx=954.11, fy=954.89, u0=471.13, v0=663.80 (piksel)

Koefisien distorsi D = [k1, k2, p1, p2, k3]:
`[0.2954, -1.8610, 0.0104, -0.0065, 3.2573]`

| Metrik | Nilai |
|---|---|
| **Mean Reprojection Error** (rata-rata RMSE per citra) | **0.8222 px** |
| RMS global (`ret` dari calibrateCamera) | 0.8371 px |
| Validasi silang (kalibrasi 12 citra, uji 13 citra lain) | 1.3969 px |

Variasi model dengan k3 dikunci 0 (`--fix-k3`): fx=958.1, fy=958.3, u0=470.6, v0=659.3, D=[0.2199, -0.8918, 0.0096, -0.0067, 0.0], MRE=0.8264 px.

## Plot dan bukti
- `reports/figures/koefisien_distorsi.png` — koefisien distorsi
- `reports/figures/error_reproyeksi.png` — error per citra
- `reports/figures/distorsi_radial.png` — profil radial + peta perpindahan piksel
- `reports/figures/cakupan_sudut.png` — sebaran sudut di bingkai
- `reports/scan/` — hasil scan papan (garis kuning tepi area 8×8)
- `reports/figures/sebelum_sesudah_undistort.jpg`, `reports/detected/` — bukti deteksi

## Catatan / keterbatasan
- Sudut papan hanya menempati bagian tengah bingkai, **tidak menjangkau tepi/pojok**. Suku orde tinggi (k2, k3) tidak terkendala di tepi; nilainya besar (k2≈-1.86, k3≈3.26) dan koreksi di pojok citra tidak dapat dipercaya. Validasi silang (1.40 px) jauh di atas MRE, tanda model distorsi orde tinggi belum stabil. K sendiri stabil (fx≈fy≈955 px pada berbagai pengaturan).
- 3 foto (17, 19, 23) tidak terdeteksi: papan terlalu miring/kecil atau hasil ekstrapolasi tidak lolos validasi.
- Error ≈0,8 px wajar untuk foto smartphone terkompres (WhatsApp, 1280×960) dengan papan kayu berkontras rendah dan garis lipatan di tengah.
- Untuk hasil lebih kuat: foto ulang dengan papan rata, isi seluruh bingkai (termasuk pojok), 15–20 pose, tanpa kompresi.

## Menjalankan ulang
```
pip install -r requirements.txt
python calibrate.py                 # default (butuh calibrate.py DAN detector.py di folder yang sama)
python calibrate.py --square-mm 30  # jika ukuran kotak berbeda
python calibrate.py --fix-k3        # k3 dikunci 0
```