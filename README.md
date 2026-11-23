# Triple E DWDM Document Control

Dashboard dan Document Management System untuk monitoring QC, ATP, dan FATP proyek DWDM Nokia yang dikerjakan PT Triple E.

## Cakupan MVP

- 16 physical sites dan 16 installation batches sesuai koreksi data proyek.
- Register QC, ATP, dan FATP untuk setiap installation batch.
- FATP Custom Builder khusus Super Admin untuk menyusun informasi perangkat, bagian, kolom, foto, caption, dan output PDF tanpa mengedit Word manual.
- Folder foto Google Drive, PIC, progress, serta status QC/ATP/FATP dipisahkan per installation batch; site multi-batch tetap dihitung satu physical site.
- Data PO, harga, expected value, SOW, dan equipment tidak disimpan.
- Upload file ke storage lokal server CasaOS.
- Preview mengirim file asli dalam mode inline tanpa public file link; kemampuan tampil mengikuti dukungan browser.
- Revision history Rev 0, Rev 1, dan seterusnya; satu revisi QC dapat memuat beberapa file.
- Nokia dapat view, preview/download, dan memberi komentar tanpa akses keputusan status.
- Keputusan Approve, Request Revision, atau Reject hanya dapat dicatat oleh Super Admin.
- Role: Super Admin, Triple E Admin, Triple E Engineer, Nokia Reviewer, Nokia Viewer.
- In-app notifications dan audit trail.
- Dark mode global yang tersimpan otomatis untuk setiap browser.
- Project Control Center dengan Attention Required, review aging, quick filter, serta register seluruh batch.
- Export report progres `.xlsx` dan `.pdf` per site dan installation batch.
- Tiga aksi upload: Draft, langsung Submit Review, dan Signed/TTD menjadi Approved khusus Super Admin.
- Super Admin dapat menghapus file pada semua status dengan audit trail dan penyesuaian status otomatis.
- Nama file ringkas: `FATP_Koba_SUM-BB-KBA-0057.docx`; nama asli tetap tercatat di metadata.
- Backup PostgreSQL terenkripsi pada storage server.
- Docker Compose untuk CasaOS pada `192.168.100.110:8095`.
- Login menggunakan username tanpa kewajiban email.

## Struktur penting

- `ARCHITECTURE.md` — blueprint database dan workflow.
- `DATA_MAPPING.md` — hasil normalisasi Excel dan format impor ideal.
- `DEPLOYMENT.md` — panduan setup dan update di CasaOS serta Cloudflare.
- `GITHUB.md` — initial push, push revisi, dan deployment update dari GitHub.
- `RESTORE.md` — prosedur pemulihan backup terenkripsi.
- `docker-compose.yml` — service web, PostgreSQL, dan backup scheduler.
- `.env.example` — seluruh konfigurasi tanpa secret asli.
- `dms/management/commands/seed_initial_data.py` — data awal 16 site/16 batch.

## Quick validation

```bash
python manage.py check
python manage.py test
```

Deployment production dijelaskan lengkap di `DEPLOYMENT.md`.

## Akun awal

Akun awal dibuat setelah container aktif menggunakan management command. Password tidak
disimpan di source code atau GitHub.

```bash
docker compose exec -it web python manage.py provision_accounts
```
