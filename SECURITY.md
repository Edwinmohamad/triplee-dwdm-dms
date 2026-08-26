# Security Notes

- Jangan commit `.env`.
- Jangan membagikan Google Client Secret, database password, atau encryption key.
- Gunakan Cloudflare Tunnel tanpa router port forwarding.
- Pertimbangkan Cloudflare Access allowlist untuk email Triple E dan Nokia sebagai lapisan tambahan.
- Review daftar pengguna setiap bulan dan nonaktifkan akun yang tidak lagi diperlukan.
- Simpan backup encryption key di luar server CasaOS.
- Tinjau Google Drive API Terms sebelum memakai upload backup database otomatis; pertimbangkan object storage S3-compatible untuk backup operasional.
- Uji restore backup minimal setiap tiga bulan.
- Semua file Approved tetap immutable; gunakan Reopen dengan alasan untuk memulai revisi baru.
