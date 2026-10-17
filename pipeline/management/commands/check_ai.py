from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from pipeline import ai


class Command(BaseCommand):
    help = (
        "Проверяет ключ ИИ-провайдера и что модели из настроек существуют. "
        "С --ping делает один короткий тестовый запрос (стоит доли цента)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--ping", action="store_true", help="Сделать тестовый запрос модели отбора")

    def handle(self, *args, **opts):
        provider = settings.AI_PROVIDER
        configured = {
            "отбор": settings.AI_CLASSIFIER_MODEL,
            "написание": settings.AI_WRITER_MODEL,
            "проверка": settings.AI_VERIFIER_MODEL,
        }
        self.stdout.write(f"Провайдер: {provider}")
        try:
            client = ai.get_client()
            available = sorted(m.id for m in client.models.list())
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Не удалось получить список моделей: {type(exc).__name__}: {exc}") from exc

        self.stdout.write("Доступные модели: " + ", ".join(available))
        missing = False
        for role, model in configured.items():
            ok = model in available
            missing |= not ok
            mark = self.style.SUCCESS("OK  ") if ok else self.style.ERROR("НЕТ ")
            price = "цена есть" if model in settings.AI_PRICING else "нет цены в AI_PRICING"
            self.stdout.write(f"{mark} {role}: {model} ({price})")

        if missing:
            self.stdout.write(self.style.WARNING(
                "Укажите существующие модели в AI_CLASSIFIER_MODEL / AI_WRITER_MODEL / AI_VERIFIER_MODEL"
            ))
        if opts["ping"]:
            from pipeline.models import AICall
            from pipeline.schemas import Verification

            result = ai.ask(
                purpose=AICall.Purpose.VERIFY, model=settings.AI_CLASSIFIER_MODEL,
                system="Ты проверяешь работу API. Ответь ok=true, confidence=1, issues=[].",
                user="Проверка связи.", output=Verification, max_tokens=1000,
            )
            self.stdout.write(self.style.SUCCESS(f"Тестовый запрос прошёл: {result.model_dump()}"))
