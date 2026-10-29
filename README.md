# Tugas Mandiri ISV - Kalibrasi Kamera

**Untuk membaca hasil, langsung buka [laporan/Laporan.pdf](laporan/Laporan.pdf).**
Tidak perlu memasang atau menjalankan apa pun jika hanya ingin membaca.
Halaman 2-3 memperlihatkan batas papan kuning, sudut, dua panel,
perataan gambar, dan pembesaran selisih pengukuran dengan proyeksi model.
Gambar juga tersedia di `audit/06_hasil_akhir/Visual_Proses.png` dan `Visual_Detail.png`.

## Menghitung ulang

Pasang Python 3.10 atau lebih baru, buka terminal di folder ini, lalu jalankan:

```bash
python mulai.py
```

Jika komputer memakai nama `python3`, gunakan `python3 mulai.py`.
Program menyiapkan kebutuhan otomatis (internet diperlukan saat pertama kali),
lalu mengerjakan seluruh tahap berurutan. Tidak ada mode yang perlu dipilih.

**Alur:** deteksi dan audit sudut -> abaikan titik celah -> dua panel -> korelasi
pola -> resolusi lebih tinggi -> hasil akhir dan laporan.

## Isi folder

- `foto/`: 29 foto asli yang dipakai.
- `data/`: ukuran kotak 44 mm, sudut awal dan catatan pengukuran; tidak perlu diedit.
- `audit/`: bukti dan angka setiap tahap, termasuk riwayat audit lama dalam ZIP.
- `laporan/`: laporan PDF dan ringkasan yang mudah dibaca.
- `materi/`: PDF kuliah sebagai acuan.

Semua foto, hasil audit, dan laporan **ikut Git**. Hanya lingkungan Python,
cache, cadangan teknis dan berkas lokal yang diabaikan. Audit lama tidak dihapus:
ada di `audit/Riwayat_Audit.zip`; arsip itu tidak perlu diekstrak untuk menjalankan tugas.

Menjalankan ulang memperbarui enam tahap audit dan laporan dengan alur yang sama.
Program ini disiapkan untuk dataset tugas tersebut, bukan aplikasi umum.
Hasil terakhir sekitar mean 0,739 px dan RMS 0,996 px; masih belum memenuhi
acuan <0,5 px pada materi. Seluruh pengerjaan memakai foto yang sudah tersedia.
