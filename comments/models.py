"""Комментарии к новостям и отзывы о бизнесах. Имя и e-mail обязательны, на сайте видно только имя.

Каждый комментарий проверяет ИИ и сам публикует или отклоняет. У отзыва о бизнесе есть оценка 1–5.
"""

import uuid
from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count, Q
from django.utils import timezone


class CommentQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Comment.Status.APPROVED).order_by("created_at")

    def since(self, hours: int = 24):
        return self.filter(created_at__gte=timezone.now() - timedelta(hours=hours))

    def rating(self) -> dict:
        """{"avg": 4.6, "count": 12} по опубликованным отзывам с оценкой."""
        data = self.filter(status=Comment.Status.APPROVED, rating__isnull=False).aggregate(
            avg=Avg("rating"), count=Count("pk"))
        return {"avg": round(data["avg"], 1) if data["avg"] else None, "count": data["count"]}


class Comment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "на проверке"
        APPROVED = "approved", "опубликован"
        REJECTED = "rejected", "отклонён"
        HIDDEN = "hidden", "скрыт по жалобам"

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    article = models.ForeignKey("news.Article", verbose_name="новость", null=True, blank=True,
                                on_delete=models.CASCADE, related_name="comments")
    listing = models.ForeignKey("directory.Listing", verbose_name="бизнес", null=True, blank=True,
                                on_delete=models.CASCADE, related_name="comments")
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)

    name = models.CharField("имя", max_length=60)
    email = models.EmailField("e-mail (не публикуется)")
    text = models.TextField("текст", max_length=2000)
    rating = models.PositiveSmallIntegerField("оценка", null=True, blank=True,
                                              validators=[MinValueValidator(1), MaxValueValidator(5)])
    ip_hash = models.CharField("IP (хэш)", max_length=32, blank=True, db_index=True)

    violation = models.CharField("нарушение", max_length=30, blank=True)
    reason = models.TextField("решение ИИ: почему", blank=True)
    public_reason = models.TextField("ответ автору", blank=True)
    attempts = models.PositiveSmallIntegerField("попыток проверки", default=0)
    reports = models.PositiveSmallIntegerField("жалоб", default=0)
    created_at = models.DateTimeField("написан", default=timezone.now, db_index=True)
    moderated_at = models.DateTimeField("проверен", null=True, blank=True)

    objects = CommentQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "комментарий"
        verbose_name_plural = "комментарии и отзывы"
        constraints = [
            models.CheckConstraint(
                condition=Q(article__isnull=False, listing__isnull=True) | Q(article__isnull=True, listing__isnull=False),
                name="comment_has_one_target",
            ),
        ]

    def __str__(self):
        return f"{self.name}: {self.text[:60]}"

    @property
    def target(self):
        return self.article or self.listing

    @property
    def is_review(self) -> bool:
        return self.listing_id is not None

    def get_absolute_url(self):
        return f"{self.target.get_absolute_url()}#comment-{self.pk}"


class CommentReport(models.Model):
    """Жалоба читателя: одна с адреса. После нескольких комментарий скрывается до решения редакции."""

    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="report_set")
    ip_hash = models.CharField(max_length=32)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "жалоба на комментарий"
        verbose_name_plural = "жалобы на комментарии"
        constraints = [models.UniqueConstraint(fields=["comment", "ip_hash"], name="one_comment_report_per_ip")]
