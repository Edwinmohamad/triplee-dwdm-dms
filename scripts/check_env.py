"""Fail closed when a production container still uses example secrets."""

import base64
import os
import sys
from urllib.parse import unquote, urlparse


def fail(message):
    print(f"Configuration error: {message}", file=sys.stderr)
    raise SystemExit(1)


required = [
    "DJANGO_SECRET_KEY",
    "DATABASE_URL",
    "POSTGRES_PASSWORD",
    "BACKUP_ENCRYPTION_KEY",
]

for name in required:
    value = os.getenv(name, "").strip()
    if not value:
        fail(f"{name} belum diisi.")
    if "replace-with" in value.lower() or "development-only" in value.lower():
        fail(f"{name} masih memakai placeholder.")

if len(os.environ["DJANGO_SECRET_KEY"]) < 50:
    fail("DJANGO_SECRET_KEY minimal 50 karakter.")

for name in ["BACKUP_ENCRYPTION_KEY"]:
    try:
        decoded = base64.urlsafe_b64decode(os.environ[name].encode())
    except Exception:
        fail(f"{name} bukan Fernet key yang valid.")
    if len(decoded) != 32:
        fail(f"{name} bukan Fernet key 32-byte yang valid.")

database_url = urlparse(os.environ["DATABASE_URL"])
if database_url.scheme not in {"postgres", "postgresql"} or database_url.hostname != "db":
    fail("DATABASE_URL harus menunjuk ke service PostgreSQL bernama db.")
if unquote(database_url.password or "") != os.environ["POSTGRES_PASSWORD"]:
    fail("Password pada DATABASE_URL tidak sama dengan POSTGRES_PASSWORD.")

print("Production environment validation passed.")
