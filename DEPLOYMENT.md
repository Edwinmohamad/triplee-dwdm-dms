# Deployment Guide — CasaOS

Target production:

- Source: `/DATA/AppData/TRIPLE-E_DMS/triplee-dwdm-dms`
- Data: `/DATA/AppData/TRIPLE-E_DMS/data`
- Logo: `/DATA/AppData/TRIPLE-E_DMS/logo.png`
- Local URL: `http://192.168.100.110:8095`
- Domain: `https://tripleedms.edwinpxmx.my.id`

## Fresh installation

Masuk ke folder source dan buat `.env`:

```bash
cd /DATA/AppData/TRIPLE-E_DMS/triplee-dwdm-dms
cp .env.example .env
python3 scripts/generate_secrets.py
```

Salin hasil secret ke `.env`. Nilai password di `DATABASE_URL` harus sama dengan `POSTGRES_PASSWORD`.

Siapkan persistent storage dan permission:

```bash
mkdir -p /DATA/AppData/TRIPLE-E_DMS/data/postgres
mkdir -p /DATA/AppData/TRIPLE-E_DMS/data/backups
mkdir -p /DATA/AppData/TRIPLE-E_DMS/data/documents
test -f /DATA/AppData/TRIPLE-E_DMS/logo.png
chown -R 1000:1000 /DATA/AppData/TRIPLE-E_DMS/data/backups
chown -R 1000:1000 /DATA/AppData/TRIPLE-E_DMS/data/documents
```

Validasi konfigurasi dan jalankan:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose exec web python manage.py check
docker compose exec web python manage.py test
curl -fsS http://192.168.100.110:8095/health/
```

Migration dan seed data dijalankan otomatis saat container web mulai.

## Update ke v1.3.0 multi-file QC

Backup database lama lebih dahulu:

```bash
cd /DATA/AppData/TRIPLE-E_DMS/triplee-dwdm-dms
docker compose exec -T db pg_dump -U triplee_dms -d triplee_dms -Fc > /DATA/AppData/TRIPLE-E_DMS/pre-v1.3.0.dump
cp .env ../env-before-v1.3.0.backup
ls -lh /DATA/AppData/TRIPLE-E_DMS/pre-v1.3.0.dump
```

Setelah source v1.3.0 sudah menggantikan source lama, hapus variabel `GOOGLE_*` dari `.env`, lalu pastikan blok berikut ada:

```dotenv
APP_DATA_DIR=/DATA/AppData/TRIPLE-E_DMS/data
DOCUMENT_STORAGE_ROOT=/app/documents
DOCUMENT_STORAGE_DISPLAY_PATH=/DATA/AppData/TRIPLE-E_DMS/data/documents
BRAND_LOGO_PATH=/app/branding/logo.png
BRAND_LOGO_FILE=/DATA/AppData/TRIPLE-E_DMS/logo.png
BACKUP_LOCAL_DIR=/app/backups
BACKUP_DAILY_RETENTION_DAYS=30
BACKUP_MONTHLY_RETENTION_DAYS=365
```

Jalankan update:

```bash
mkdir -p /DATA/AppData/TRIPLE-E_DMS/data/documents
chown -R 1000:1000 /DATA/AppData/TRIPLE-E_DMS/data/documents
test -f /DATA/AppData/TRIPLE-E_DMS/logo.png

docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose exec web python manage.py showmigrations dms
docker compose exec web python manage.py check
docker compose exec web python manage.py test
curl -fsS http://192.168.100.110:8095/health/
curl -fsSI http://192.168.100.110:8095/branding/logo/
```

Migration `0003_local_server_storage` menghapus kredensial OAuth dan mengganti referensi Drive dengan storage key lokal. Data site, batch, status, user, review, komentar, notifikasi, dan audit log tetap dipertahankan.

## Struktur file dokumen

Folder dibuat otomatis ketika upload:

```text
data/documents/
└── PROJECT-CODE/
    └── TOWER-ID_SITE-NAME/
        └── BATCH-01_BATCH-LABEL/
            └── QC/
                └── REV-000/
                    └── TOWER-ID_BATCH-01_QC_REV-000_YYYYMMDD.pdf
```

Pengguna Nokia mengunduh file melalui DMS; folder host tidak perlu dibagikan langsung.

## Cloudflare Tunnel

Gunakan Published Application berikut:

```text
Hostname: tripleedms.edwinpxmx.my.id
Service:  http://192.168.100.110:8095
```

Tidak diperlukan router port forwarding.

## Backup

- Backup PostgreSQL terenkripsi berjalan setiap hari pukul 02.00 WIB.
- Daily backup disimpan 30 hari.
- Monthly backup disimpan 365 hari.
- Lokasi host: `/DATA/AppData/TRIPLE-E_DMS/data/backups`.
- Simpan `BACKUP_ENCRYPTION_KEY` di password manager.
- Salin folder `data` ke disk/perangkat lain secara berkala; backup pada disk yang sama bukan perlindungan penuh terhadap kerusakan server.

## GitHub update

```bash
cd /DATA/AppData/TRIPLE-E_DMS/triplee-dwdm-dms
git status
git add .
git commit -m "Use local server storage and improve site register"
git push origin main
gh run list --repo Edwinmohamad/triplee-dwdm-dms --limit 3
```

Pastikan `.env`, folder data, dokumen, backup, dan file zip tidak ikut commit.

## Troubleshooting

```bash
docker compose ps
docker compose logs --tail=150 web
docker compose logs --tail=100 db
docker compose logs --tail=100 backup
ls -l /DATA/AppData/TRIPLE-E_DMS/logo.png
ls -ld /DATA/AppData/TRIPLE-E_DMS/data/documents
```

Jika upload gagal karena permission:

```bash
chown -R 1000:1000 /DATA/AppData/TRIPLE-E_DMS/data/documents
docker compose restart web
```
