# Restore Backup Database

Restore mengganti isi database aktif. Pastikan file dan `BACKUP_ENCRYPTION_KEY` benar sebelum menjalankannya.

## 1. Pilih dan dekripsi backup

File backup berada di:

```text
/DATA/AppData/TRIPLE-E_DMS/data/backups
```

Salin file yang dipilih menjadi `restore.dump.fernet`, lalu dekripsi:

```bash
cd /DATA/AppData/TRIPLE-E_DMS/triplee-dwdm-dms
docker compose run --rm --entrypoint python web -c "import os,pathlib; from cryptography.fernet import Fernet; src=pathlib.Path('/app/backups/restore.dump.fernet'); pathlib.Path('/app/backups/restore.dump').write_bytes(Fernet(os.environ['BACKUP_ENCRYPTION_KEY'].encode()).decrypt(src.read_bytes()))"
```

## 2. Restore PostgreSQL

```bash
docker compose stop web backup
docker cp /DATA/AppData/TRIPLE-E_DMS/data/backups/restore.dump triplee-dms-db:/tmp/restore.dump
docker compose exec db pg_restore --clean --if-exists --no-owner --no-acl --username triplee_dms --dbname triplee_dms /tmp/restore.dump
docker compose up -d
docker compose ps
```

Login dan periksa jumlah site, batch, dokumen, pengguna, serta halaman Storage Server. Setelah verifikasi, hapus file `restore.dump` yang tidak terenkripsi dari host dan container.

Database hanya menyimpan metadata file. Untuk pemulihan lengkap, folder `/DATA/AppData/TRIPLE-E_DMS/data/documents` harus ikut dipulihkan dari salinan data Anda.
