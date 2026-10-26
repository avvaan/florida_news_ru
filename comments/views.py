from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from directory.models import Category, Listing
from directory.views import ip_hash
from news.models import Article

from . import moderation
from .forms import CommentForm
from .models import Comment


def get_target(kind: str, pk: int):
    if kind == "article":
        return get_object_or_404(Article.objects.published(), pk=pk)
    return get_object_or_404(Listing, pk=pk, is_active=True, category__kind=Category.Kind.BUSINESS)


def too_many(key: str, email: str) -> str:
    recent = Comment.objects.filter(ip_hash=key)
    if recent.since(1).count() >= moderation.MAX_PER_IP_PER_HOUR or \
            recent.since(24).count() >= moderation.MAX_PER_IP_PER_DAY:
        return "С вашего адреса уже много комментариев. Попробуйте позже."
    if Comment.objects.since(24).filter(email__iexact=email).count() >= moderation.MAX_PER_EMAIL_PER_DAY:
        return "С этого e-mail уже много комментариев за сутки. Попробуйте завтра."
    return ""


@require_POST
@never_cache
def add(request, kind, pk):
    target = get_target(kind, pk)
    form = CommentForm(request.POST, kind=kind, pk=pk)
    if form.is_valid():
        if form.is_bot:  # бот заполнил скрытое поле — делаем вид, что всё хорошо, и ничего не сохраняем
            return redirect(f"{target.get_absolute_url()}#comments")
        key = ip_hash(request)
        if error := too_many(key, form.cleaned_data["email"]):
            form.add_error(None, error)
        else:
            comment = form.save(commit=False)
            setattr(comment, kind, target)
            comment.ip_hash = key
            comment.save()
            moderation.start_moderation(comment)
            return redirect(f"{target.get_absolute_url()}?comment={comment.token}#my-comment")
    # Ошибки показываем на отдельной странице с той же формой — без повторной сборки страницы новости.
    return render(request, "comments/form_page.html", {"form": form, "target": target, "kind": kind}, status=400)


@require_POST
def report(request, pk):
    comment = get_object_or_404(Comment, pk=pk, status=Comment.Status.APPROVED)
    moderation.report(comment, ip_hash(request))
    return redirect(f"{comment.target.get_absolute_url()}?reported={comment.pk}#comment-{comment.pk}")
