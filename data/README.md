# Dataset

`photos/` berisi 29 foto asli. Seluruh foto telah dipindahkan dari dua kelompok
percobaan lama tanpa mengubah byte berkasnya. Hash SHA-256 dan kategori lama
tersimpan di `dataset_manifest.json`.

`initial_corners.npz` adalah inisialisasi sudut dari dataset yang sudah diaudit,
bukan koordinat akhir yang langsung dipakai untuk kalibrasi. Program mengukur
ulang sudut dari gambar setiap kali dijalankan. Inisialisasi dan pengecualian
titik hanya diterapkan bila hash foto dan ukuran pola cocok.

Untuk foto lain, gunakan `--photos /lokasi/foto`; program mencoba deteksi otomatis.
Foto yang gagal tidak diisi dengan titik buatan. Kalibrasi berhenti jika kurang
dari minimum foto yang ditentukan pada konfigurasi.
