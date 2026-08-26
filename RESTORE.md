# Restore Backup Database

Restore adalah prosedur darurat dan akan mengganti isi database aktif. Jalankan hanya setelah memastikan file dan encryption key benar.

## 1. Ambil dan dekripsi backup

1. Unduh file `.dump.fernet` dari `TripleE-DWDM-DMS/Database-Backup` di Google Drive.
2. Salin file ke `/DATA/AppData/triplee-dwdm-dms/backups/restore.dump.fernet`.
3. Dari folder aplikasi, dekripsi menggunakan container aplikasi dan key dari `.env`:

```bash
docker compose run --rm --entrypoint python web -c "import os,pathlib; from cryptography.fernet import Fernet; src=pathlib.Path('/app/backups/restore.dump.fernet'); pathlib.Path('/app/backups/restore.dump').write_bytes(Fernet(os.environ['BACKUP_ENCRYPTION_KEY'].encode()).decrypt(src.read_bytes()))"
```

## 2. Restore PostgreSQL

Hentikan proses yang dapat menulis ke database, lalu copy file hasil dekripsi ke container database:

```bash
docker compose stop web backup
docker cp /DATA/AppData/triplee-dwdm-dms/backups/restore.dump triplee-dms-db:/tmp/restore.dump
```

Setelah itu jalankan restore:

```bash
docker compose exec db pg_restore --clean --if-exists --no-owner --no-acl --username triplee_dms --dbname triplee_dms /tmp/restore.dump
```

Setelah sukses:

```bash
docker compose up -d
docker compose ps
```

Login dan periksa jumlah site, batch, dokumen, pengguna, serta koneksi Google Drive. Hapus file `restore.dump` yang tidak terenkripsi dari host dan container setelah verifikasi.
