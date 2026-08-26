# Data Mapping Tracker Excel

## Keputusan transformasi

Tracker awal dipakai hanya untuk membentuk register dokumen. Data PO Received, nilai/harga, expected, SOW, dan scope equipment tidak diimpor.

Hasil normalisasi awal:

| Entitas | Jumlah | Aturan |
|---|---:|---|
| Physical site | 16 | Satu `tower_id` mewakili satu site fisik |
| Installation batch | 18 | Setiap jadwal/gelombang instalasi menjadi batch terpisah |
| Document register | 54 | QC, ATP, dan FATP untuk setiap batch |

Mentigi Batch 1 dan Batch 2 memakai `tower_id` yang sama, demikian juga Sungai Liat Batch 1 dan Batch 2. Keduanya tetap merupakan batch dokumen yang berbeda. Tanjung Pandan MTI dimulai dengan status `Pending Installation`, sehingga upload dokumennya terkunci sampai status instalasi diperbarui.

Normalisasi status awal dari kolom `QC READY`, `ATP READY`, dan `FATP READY`:

| Nilai tracker | Status DMS | Alasan |
|---|---|---|
| `SIGNED` | `APPROVED` | Dokumen sudah ditandatangani |
| `DONE SUBMIT` | `UNDER_REVIEW` | Sudah diserahkan dan menunggu keputusan Nokia |
| `ADDIONAL FOTO WAITING PERMIT` | `REVISION_REQUIRED` | Ada kelengkapan/foto yang masih harus ditindaklanjuti |
| `NOT POWER ON YET`, `NOT STARTED YET` | `NOT_STARTED` | Dokumen belum siap |
| `COMBINED ...` atau `N/A COMBINED ...` | `NOT_STARTED` + import note | Desain baru mewajibkan dokumen terpisah untuk setiap batch |

Workbook sumber tidak mempunyai tanggal jadwal instalasi yang terstruktur. Karena itu `scheduled_date` tidak ditebak dan dibiarkan kosong untuk diisi melalui halaman Edit Batch.

## Struktur spreadsheet ideal untuk impor berikutnya

Gunakan satu baris per installation batch, tanpa merged cells.

| Kolom | Contoh | Wajib | Catatan |
|---|---|---:|---|
| `project_code` | `NOKIA-DWDM` | Ya | Kode projek stabil |
| `tower_id` | `SUM-BB-TDN-0361` | Ya | ID site fisik; boleh berulang untuk batch berbeda |
| `site_name` | `MENTIGI` | Ya | Nama tampilan |
| `region` | `BANGKA BELITUNG` | Ya | Region operasional |
| `batch_no` | `2` | Ya | Unik di dalam satu `tower_id` |
| `batch_label` | `Batch 2` | Ya | Label pengguna |
| `pic_name` | `ROBI` | Tidak | PIC instalasi/dokumen |
| `scheduled_date` | `2026-08-30` | Tidak | Format ISO `YYYY-MM-DD` |
| `installed_at` | `2026-09-02` | Tidak | Kosong jika belum terpasang |
| `installation_status` | `INSTALLED` | Ya | Nilai terkontrol di bawah |
| `qc_status` | `APPROVED` | Ya | Status register QC |
| `atp_status` | `UNDER_REVIEW` | Ya | Status register ATP |
| `fatp_status` | `NOT_STARTED` | Ya | Status register FATP |
| `note` | `Jadwal batch berbeda` | Tidak | Catatan singkat |

Nilai `installation_status` yang diterima: `PENDING_INSTALLATION`, `INSTALLED`, `DOCUMENT_PREPARATION`, `COMPLETED`.

Nilai status dokumen yang diterima: `NOT_STARTED`, `DRAFT`, `UPLOADED`, `UNDER_REVIEW`, `REVISION_REQUIRED`, `APPROVED`, `REJECTED`, `NOT_APPLICABLE`.

## Aturan integritas

1. Kunci site adalah gabungan `project_code + tower_id`.
2. Kunci batch adalah gabungan `project_code + tower_id + batch_no`.
3. Satu batch selalu mempunyai tepat satu register QC, ATP, dan FATP.
4. File tidak ditempel atau ditautkan pada Excel; file dikelola lewat DMS dan storage server.
5. Seed hanya membuat data yang belum ada. Menjalankan ulang container tidak mengembalikan status yang sudah diubah pengguna.
6. Status dan tanggal baru harus diubah melalui aplikasi agar audit trail tetap lengkap.
