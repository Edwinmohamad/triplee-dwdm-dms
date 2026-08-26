# GitHub Setup — Triple E DMS

Repository harus dibuat **Private** karena aplikasi memuat workflow dan struktur internal
PT Triple E. File `.env`, database, dokumen, backup, dan private key sudah dikecualikan
melalui `.gitignore`.

## Initial push dari CasaOS

```bash
cd /DATA/AppData/TRIPLE-E_DMS/triplee-dwdm-dms

git init
git branch -M main
git config user.name "Edwin Mohamad"
git config user.email "Edwinmohamad@users.noreply.github.com"

git check-ignore -v .env
git add .
git status --short
git commit -m "Initial Triple E DWDM DMS"

gh auth login
gh repo create Edwinmohamad/triplee-dwdm-dms \
  --private \
  --source=. \
  --remote=origin \
  --push
```

Sebelum menjalankan `git commit`, pastikan `.env` tidak muncul pada `git status`.

## Push revisi berikutnya

```bash
cd /DATA/AppData/TRIPLE-E_DMS/triplee-dwdm-dms
git status
git add .
git commit -m "Jelaskan revisi di sini"
git push origin main
```

## Menarik revisi ke CasaOS dan deploy

Jalankan backup database terlebih dahulu, kemudian:

```bash
cd /DATA/AppData/TRIPLE-E_DMS/triplee-dwdm-dms
git pull --ff-only origin main
docker compose up -d --build
docker compose ps
curl -fsS http://192.168.100.110:8095/health/
```

Migration database otomatis dijalankan oleh `entrypoint.sh` ketika container web dimulai.
Workflow GitHub Actions pada `.github/workflows/tests.yml` menjalankan Django check dan test
setiap kali ada push atau pull request.
