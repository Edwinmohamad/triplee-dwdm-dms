# Changelog

## 1.4.0

- Menghilangkan kotak putih logo dan membersihkan background putih dari tepi gambar logo di browser.
- Menambahkan dark mode global dengan pilihan tema yang tersimpan di browser.
- Mendesain ulang dashboard dengan progress ring, status distribution, dan visual per tipe dokumen.
- Menambahkan export laporan progres Excel berisi Ringkasan, Progress Site, Detail Batch, dan Riwayat Dokumen.
- Menambahkan chart, formula persentase, filter, serta conditional formatting pada report Excel.
- Menambahkan tombol hapus per file untuk tim Triple E selama revisi masih terbuka dan belum disubmit.
- Menjaga file pada revisi terkunci agar tidak dapat dihapus oleh Nokia maupun pengguna internal.

## 1.3.1

- Menambahkan loader global dengan animasi logo Triple E saat halaman dibuka atau dimuat ulang.
- Menampilkan loader khusus upload berisi jumlah file dan total ukuran upload.
- Menonaktifkan tombol upload setelah submit untuk mencegah upload ganda.
- Menambahkan loading state pada navigasi dan penyimpanan form.

## 1.3.0

- Menambahkan beberapa attachment dalam satu revisi QC.
- Upload QC berikutnya sebelum submit ditambahkan ke revisi yang sama.
- Menambahkan preview/download per file dan download seluruh revisi sebagai ZIP.
- Auto-rename file memakai nama site, Tower ID, batch, tipe dokumen, revisi, dan nomor file.
- Membatasi Nokia ke view, preview/download, dan komentar tanpa keputusan status.
- Memindahkan akses keputusan Approve/Revision/Reject menjadi khusus Super Admin.
- Memigrasikan metadata file lama menjadi attachment pertama tanpa memindahkan file fisik.

## 1.2.1

- Memperbaiki tombol upload yang terkunci pada dokumen historis berstatus `UNDER_REVIEW` tanpa file.
- Upload pertama pada dokumen historis mempertahankan status review/approved dan langsung mengunci versinya.

## 1.2.0

- Mengganti Google Drive/OAuth dengan penyimpanan dokumen lokal di server CasaOS.
- Menyusun folder dokumen otomatis per project, site, installation batch, tipe, dan revisi.
- Menambahkan halaman status kapasitas Storage Server.
- Menggunakan logo dari `/DATA/AppData/TRIPLE-E_DMS/logo.png` dengan fallback `3E`.
- Mengubah halaman Site dari card grid menjadi document register yang dapat dicari dan difilter.
- Menjaga preview/download Nokia melalui autentikasi aplikasi.
- Mengubah backup database menjadi local encrypted backup dengan retensi harian dan bulanan.
- Menambahkan migration penghapusan kredensial OAuth serta penggantian Drive file ID menjadi local storage key.
