# Deployment Guide — CasaOS

Target:

- CasaOS IP: `192.168.100.110`
- Web port: `8095`
- Domain: `tripleedms.edwinpxmx.my.id`
- Resource: 4 CPU, 8 GB RAM, 1 TB storage

## 1. Prepare folder

Copy seluruh project ke:

```text
/DATA/AppData/triplee-dwdm-dms/app
```

Masuk ke folder tersebut dan copy konfigurasi:

```bash
cp .env.example .env
```

## 2. Generate secrets

Jalankan perintah berikut. Script ini hanya memakai Python standard library.

```bash
python3 scripts/generate_secrets.py
```

Salin keempat nilai ke `.env`. Gunakan nilai `POSTGRES_PASSWORD` yang sama pada `DATABASE_URL`. Jika password misalnya `abc123`, maka URL-nya menjadi `postgresql://triplee_dms:abc123@db:5432/triplee_dms`.

Jangan mengirim atau menyimpan secret di GitHub/chat.

## 3. Google Cloud OAuth

1. Buka Google Cloud Console.
2. Buat project, misalnya `Triple E DMS`.
3. Aktifkan **Google Drive API**.
4. Atur OAuth consent screen sebagai External atau Internal sesuai akun.
5. Buat OAuth Client ID tipe **Web application**.
6. Tambahkan Authorized redirect URI:

```text
https://tripleedms.edwinpxmx.my.id/integrations/google-drive/callback/
```

7. Isi `GOOGLE_OAUTH_CLIENT_ID` dan `GOOGLE_OAUTH_CLIENT_SECRET` pada `.env`.
8. Saat status OAuth masih **Testing**, tambahkan akun Google pribadi Anda sebagai Test user.
9. Sebelum dipakai rutin, ubah Publishing status menjadi **In production**. Refresh token pada mode Testing dapat kedaluwarsa setelah tujuh hari.

Aplikasi hanya meminta scope `drive.file`, yaitu scope per-file non-sensitive yang direkomendasikan Google. Nokia tidak perlu login atau diberi akses langsung ke Google Drive.

## 4. Start containers

Siapkan folder data dan hak akses backup terlebih dahulu:

```bash
mkdir -p /DATA/AppData/triplee-dwdm-dms/postgres
mkdir -p /DATA/AppData/triplee-dwdm-dms/backups
chown -R 1000:1000 /DATA/AppData/triplee-dwdm-dms/backups
```

Kemudian build dan jalankan container:

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose exec web python manage.py check
```

Tes dari jaringan lokal:

```text
http://192.168.100.110:8095/health/
```

Respons yang benar:

```json
{"status":"ok","service":"triplee-dwdm-dms"}
```

Sebelum memasukkan dokumen produksi, jalankan test suite sekali:

```bash
docker compose exec web python manage.py test
```

## 5. Cloudflare Tunnel

Pada tunnel yang sudah aktif, tambahkan Published Application:

```text
Hostname: tripleedms.edwinpxmx.my.id
Service:  http://192.168.100.110:8095
```

Tidak perlu port forwarding pada router.

## 6. Initial setup

1. Buat akun awal dari terminal CasaOS. Password tidak disimpan dalam source code.

```bash
docker compose exec -it web python manage.py provision_accounts
```

2. Buka `https://tripleedms.edwinpxmx.my.id/login/` dan login menggunakan username.
3. Akun `user` memiliki role Nokia Reviewer: view, download, komentar, dan review; tanpa akses upload.
4. Buka **Google Drive** pada sidebar.
5. Klik **Connect Google Drive** dan login menggunakan akun Google pribadi.
6. Tambahkan pengguna Triple E dan Nokia dari halaman **Pengguna**.

Folder berikut dibuat otomatis:

```text
TripleE-DWDM-DMS/
├── NOKIA-DWDM_Nokia-DWDM-Document-Project/
└── Database-Backup/
```

## 7. Backup

- Scheduler menjalankan backup setiap hari pukul 02.00 WIB.
- Backup database dienkripsi sebelum keluar dari server.
- Backup lokal: 7 hari.
- Google Drive daily backup: 30 hari.
- Monthly backup: 365 hari.

Simpan `BACKUP_ENCRYPTION_KEY` di password manager. Tanpa key tersebut, backup tidak dapat dipulihkan.

> Catatan kebijakan: Google Drive API Terms membatasi penggunaan API untuk backup konten aplikasi tanpa persetujuan tertulis Google. Fitur upload backup disediakan sesuai kebutuhan internal ini, tetapi PT Triple E perlu memeriksa kebijakan tersebut sebelum mengaktifkannya untuk operasional. Alternatif yang lebih jelas untuk backup database otomatis adalah penyimpanan S3-compatible; file dokumen tetap dapat memakai Google Drive.

Referensi resmi: [Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [OAuth production readiness](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification), dan [Drive API Terms](https://developers.google.com/workspace/drive/api/terms).

## 8. Update application

Sebelum update, jalankan backup manual dari halaman Admin. Setelah source code baru disalin:

```bash
docker compose build
docker compose up -d
docker compose ps
```

Migration database dijalankan otomatis ketika web container mulai.

## 9. Troubleshooting singkat

```bash
docker compose ps
docker compose logs --tail=100 web
docker compose logs --tail=100 db
docker compose logs --tail=100 backup
```

Jika Google OAuth menampilkan redirect mismatch, pastikan URI di Google Cloud sama persis dengan URI pada `.env`, termasuk `https` dan garis miring terakhir setelah `/callback/`.
