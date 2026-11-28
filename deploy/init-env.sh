#!/usr/bin/env bash
# Создаёт deploy/.env.prod из deploy/env.prod.example со сгенерированными
# секретами: DJANGO_SECRET_KEY и пароль базы (он же — в DATABASE_URL).
# Ключи API и токен туннеля вписываются руками после.
#
#   bash deploy/init-env.sh
set -euo pipefail
cd "$(dirname "$0")"

target=.env.prod
if [ -e "$target" ]; then
    echo "deploy/$target уже есть; оставляю как есть." >&2
    exit 1
fi

random_hex() { od -An -tx1 -N"$1" /dev/urandom | tr -d ' \n'; }
secret_key=$(random_hex 32)   # 64 hex-символа
db_password=$(random_hex 24)  # 48 hex-символов: безопасно внутри URL

umask 077                     # файл читает только владелец
sed -e "s/^DJANGO_SECRET_KEY=.*/DJANGO_SECRET_KEY=$secret_key/" \
    -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$db_password/" \
    -e "s/POSTGRES_PASSWORD_HERE/$db_password/" \
    env.prod.example > "$target"

echo "Создан deploy/$target с новым DJANGO_SECRET_KEY и паролем базы."
echo "Теперь впишите ключи API и TUNNEL_TOKEN:  nano deploy/$target"
