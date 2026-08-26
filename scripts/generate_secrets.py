"""Generate production secrets using only the Python standard library."""

import base64
import secrets


def fernet_key():
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


print(f"DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}")
print(f"GOOGLE_TOKEN_ENCRYPTION_KEY={fernet_key()}")
print(f"BACKUP_ENCRYPTION_KEY={fernet_key()}")
print(f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}")
