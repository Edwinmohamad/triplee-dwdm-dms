# Changelog

## 1.7.4

- Mengoreksi Mentigi dan HUT. Sungai Liat agar masing-masing hanya memiliki Batch 1.
- Mengubah total proyek menjadi 16 site, 16 installation batch, dan 48 register dokumen.
- Menambahkan migration pembersihan dua Batch 2 duplikat dengan pemeriksaan keamanan data.
- Membuat jumlah batch pada hero dashboard mengikuti data aktif, bukan angka statis.

## 1.7.3

- Mengubah tombol Buka Foto Google Drive agar selalu terbuka di tab browser baru.
- Menghapus perilaku popup dan fallback jendela popup dari JavaScript.
- Menambahkan proteksi `noopener noreferrer` pada tautan eksternal Google Drive.

## 1.7.2

- Memperbaiki Server Error 500 ketika Super Admin mengubah status dokumen secara manual.
- Menambahkan kolom catatan perubahan status yang bersifat opsional.
- Menjaga endpoint tetap kompatibel dengan halaman lama/cache browser yang hanya mengirim pilihan status.
- Menambahkan pengujian perubahan status tanpa catatan agar regresi tidak terulang.

## 1.7.1

- Menyederhanakan FATP Builder menjadi alur upload-first yang lebih ringkas dan mudah digunakan.
- Menambahkan tujuh bagian default otomatis sesuai PDF contoh FATP Koba.
- Menyembunyikan pengaturan judul, model perangkat, kolom, page break, urutan, dan bagian custom sebagai opsi lanjutan.
- Menampilkan progress bagian terisi, jumlah foto, upload multi-foto langsung, dan output PDF pada panel yang mudah dijangkau.
- Mengisi builder lama yang masih kosong melalui migration tanpa mengubah builder yang sudah memiliki bagian atau foto.

## 1.7.0

- Menambahkan FATP Custom Builder khusus Super Admin dengan informasi site, tanggal instalasi, PIC, deskripsi pekerjaan, dan daftar perangkat dinamis.
- Mengizinkan Super Admin menambah, menghapus, mengurutkan, serta mengubah bagian FATP secara bebas.
- Mendukung jumlah foto bebas pada setiap bagian dengan pilihan layout 1, 2, atau 3 kolom.
- Menambahkan upload multi-foto, caption, urutan foto, preview PDF, page break, dan generate revisi FATP langsung ke DMS.
- Menghasilkan PDF Letter native dengan foto auto-orient, rasio gambar terjaga, tabel perangkat, kotak foto, header, footer, dan nomor halaman.
- Mengizinkan Super Admin memilih status apa pun ketika menghasilkan FATP dan tetap menyediakan kontrol status manual.
- Memindahkan folder foto Google Drive dari level site ke level installation batch tanpa menghapus link lama.
- Menampilkan seluruh batch di bawah satu site beserta PIC, status QC/ATP/FATP, progress, dan folder foto masing-masing.
- Menjaga metrik utama pada 16 physical site dan 18 installation batch.
- Mengizinkan file yang sama diunggah kembali ketika membuat revisi dokumen baru.

## 1.6.2

- Menghapus card dan background putih di belakang logo Nokia serta Triple E.
- Memproses background putih kedua logo menjadi transparan di browser.
- Mengubah dual-brand header menjadi corporate dark minimal dengan logo monokrom.
- Mengurangi neon cyan, ornament lingkaran, shadow, dan border dekoratif yang berlebihan.
- Mengubah hero dashboard ke tema navy-slate dengan aksen biru enterprise yang lebih tenang.

## 1.6.1

- Menambahkan Kontrol Status Super Admin pada setiap detail dokumen.
- Mengizinkan Super Admin menetapkan status apa pun tanpa mengikuti urutan workflow normal.
- Menjaga file dan riwayat revisi saat status diubah secara manual.
- Menyesuaikan timestamp submitted/approved dan penguncian versi untuk Under Review serta Approved.
- Mencatat status lama, status baru, dan catatan opsional ke Audit Log.

## 1.6.0

- Menambahkan dual-brand dashboard dengan Nokia sebagai Customer dan Triple E sebagai Implementation Vendor.
- Menambahkan endpoint dan mount read-only khusus `nokialogo.png` dengan fallback wordmark apabila file tidak tersedia.
- Mengganti seluruh simbol menu sidebar dengan ikon SVG modern dan konsisten.
- Menambahkan state hover, active glow, ikon notifikasi baru, dukungan dark mode, dan layout dual-brand responsif mobile.

## 1.5.3

- Membuka tombol Buka Foto dalam popup Google Drive yang terpisah dari halaman DMS.
- Menempatkan popup di tengah layar dengan ukuran responsif desktop.
- Menambahkan fallback tab baru apabila popup diblokir atau perangkat tidak mendukung popup.

## 1.5.2

- Memindahkan Foto Instalasi dari dashboard utama menjadi menu dan halaman khusus.
- Mengubah tampilan menjadi split view: daftar site di kiri dan detail folder di kanan.
- Menambahkan pencarian serta filter region dan status tanpa reload halaman.
- Menampilkan aksi Buka Foto dan Salin Link hanya pada site yang telah terhubung.
- Menempatkan pengaturan folder Google Drive secara inline pada panel detail khusus admin.
- Menambahkan tampilan responsif mobile dan dark mode untuk halaman Foto Instalasi.

## 1.5.1

- Memperbaiki loader yang dapat tetap aktif setelah download atau preview selesai.
- Loader kini hanya muncul untuk navigasi internal dan submit form, lalu otomatis dibersihkan saat halaman/tab kembali aktif.
- Menambahkan menu Foto Instalasi langsung di dashboard tanpa popup.
- Menambahkan link folder Google Drive per site dengan pencarian, salin link, buka di tab yang sama, dan pengaturan inline untuk admin.
- Menyimpan link folder saja tanpa OAuth Client Secret atau kredensial Google di DMS.

## 1.5.0

- Mengubah dashboard menjadi Project Control Center dengan progress per tipe dokumen, KPI strip, Attention Required, dan review aging.
- Menambahkan register 18 installation batch langsung di dashboard beserta filter Site ID, tipe dokumen, status, dan PIC.
- Memperbaiki pencarian/filter Site yang sebelumnya tampak stuck dengan fallback CSS, null guard JavaScript, dan tombol Reset.
- Menambahkan quick filter Under Review, Perlu Revisi, dan Belum Upload.
- Menambahkan export laporan progress PDF berisi ringkasan, prioritas, serta status QC/ATP/FATP per batch.
- Menambahkan tiga aksi upload: Simpan Draft, Upload & Submit Review, dan Upload Signed/TTD menjadi Approved.
- Membatasi aksi Signed/Approved hanya untuk Super Admin dan mencatat keputusan otomatis pada audit/review history.
- Mengizinkan Super Admin mengunggah revisi signed langsung dari dokumen berstatus Under Review.
- Mengembalikan preview ke file asli dengan Content-Disposition inline tanpa konversi format.

## 1.4.1

- Menyederhanakan nama file menjadi `TYPE_Nama-Site_SITE-ID.ext`, misalnya `FATP_Koba_SUM-BB-KBA-0057.docx`.
- Menambahkan akhiran `_02`, `_03`, dan seterusnya hanya untuk attachment QC tambahan.
- Menerapkan nama pendek pada file lama saat ditampilkan, diunduh, atau dimasukkan ke ZIP tanpa memindahkan file fisik.
- Memberikan Super Admin akses hapus pada semua status, termasuk Under Review dan Approved.
- Menyimpan tombstone dan riwayat review saat file terakhir dari revisi terkunci dihapus.
- Menyesuaikan status dokumen otomatis setelah file terakhir dihapus.
- Menghapus perilaku sticky panel upload agar tidak menutupi Reopen dan panel di bawahnya saat scroll.

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
