"""Пользователь-агент для API: сотрудник без пароля и входа в админку, только ключ.

    python manage.py setup_agent                 # создать (или показать) ключ и вывести его
    python manage.py setup_agent --rotate        # выпустить новый ключ, старый перестанет работать
    AGENT_API_TOKEN=<40 hex> python manage.py setup_agent   # взять ключ из переменной (так делает build.sh)
"""

import os
import re

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from rest_framework.authtoken.models import Token

TOKEN_RE = re.compile(r"^[0-9a-f]{40}$")


class Command(BaseCommand):
    help = "Создаёт пользователя-агента (is_staff) и ключ API для него"

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.environ.get("AGENT_API_USER", "agent"))
        parser.add_argument("--token", default=os.environ.get("AGENT_API_TOKEN", ""),
                            help="Готовый ключ: 40 символов 0-9a-f (по умолчанию — из AGENT_API_TOKEN)")
        parser.add_argument("--rotate", action="store_true", help="Выпустить новый случайный ключ")
        parser.add_argument("--quiet", action="store_true", help="Не печатать ключ (для build.sh)")

    def handle(self, *args, username, token, rotate, quiet, **options):
        token = token.strip().lower()
        if token and not TOKEN_RE.match(token):
            raise CommandError("Ключ должен быть из 40 символов 0-9 и a-f, например: python -c "
                               "\"import secrets; print(secrets.token_hex(20))\"")
        user, created = User.objects.get_or_create(username=username, defaults={"is_staff": True})
        if created:
            user.set_unusable_password()
        user.is_staff, user.is_active = True, True
        user.save()

        current = Token.objects.filter(user=user).first()
        if token:
            if not current or current.key != token:
                Token.objects.filter(user=user).delete()
                Token.objects.filter(key=token).exclude(user=user).delete()
                current = Token.objects.create(user=user, key=token)
                self.stdout.write(f"Агент «{username}»: ключ из переменной AGENT_API_TOKEN установлен")
            elif not quiet:
                self.stdout.write(f"Агент «{username}»: ключ уже установлен")
        elif rotate or not current:
            Token.objects.filter(user=user).delete()
            current = Token.objects.create(user=user)
            self.stdout.write(f"Агент «{username}»: выпущен новый ключ")
        if not quiet:
            self.stdout.write(f"Authorization: Token {current.key}")
