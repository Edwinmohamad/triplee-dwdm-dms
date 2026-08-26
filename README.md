# Triple E DWDM Document Control

Dashboard dan Document Management System untuk monitoring QC, ATP, dan FATP proyek DWDM Nokia yang dikerjakan PT Triple E.

## Cakupan MVP

- 16 physical sites dan 18 installation batches dari tracker awal.
- Register QC, ATP, dan FATP untuk setiap installation batch.
- Data PO, harga, expected value, SOW, dan equipment tidak disimpan.
- Upload file ke storage lokal server CasaOS.
- Preview dan download melalui DMS tanpa public file link.
- Revision history Rev 0, Rev 1, dan seterusnya.
- Review Nokia: Approve, Request Revision, Reject, dan komentar.
- Role: Super Admin, Triple E Admin, Triple E Engineer, Nokia Reviewer, Nokia Viewer.
- In-app notifications dan audit trail.
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
- `dms/management/commands/seed_initial_data.py` — data awal 16 site/18 batch.

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
