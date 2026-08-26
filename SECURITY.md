# Security Notes

- Jangan commit `.env`.
- Jangan membagikan database password atau backup encryption key.
- Gunakan Cloudflare Tunnel tanpa router port forwarding.
- Pertimbangkan Cloudflare Access allowlist untuk email Triple E dan Nokia sebagai lapisan tambahan.
- Review daftar pengguna setiap bulan dan nonaktifkan akun yang tidak lagi diperlukan.
- Simpan backup encryption key di luar server CasaOS.
- Salin backup terenkripsi ke perangkat fisik atau lokasi lain secara berkala agar kerusakan disk server tidak menghilangkan database dan backup sekaligus.
- Uji restore backup minimal setiap tiga bulan.
- Semua file Approved tetap immutable; gunakan Reopen dengan alasan untuk memulai revisi baru.
