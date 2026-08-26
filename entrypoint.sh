#!/bin/sh
set -eu

python scripts/check_env.py
python manage.py migrate --noinput
python manage.py seed_initial_data

exec "$@"
