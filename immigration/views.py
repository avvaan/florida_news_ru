from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core.i18n import current_language

from . import accounts, assistant
from .forms import AskForm, CodeForm, LoginForm, RegionForm
from .models import AssistantSettings, Question, Reader

SESSION_EMAIL = "imm_login_email"
SESSION_CONSENT = "imm_login_consent"
HISTORY = 20


def _reader(user):
    return getattr(user, "reader", None) if user.is_authenticated else None


@never_cache
def page(request):
    conf = AssistantSettings.load()
    user = request.user
    allowed = assistant.can_use(user)
    form = AskForm(request.POST or None, max_chars=conf.max_question_chars)
    if request.method == "POST":
        if not allowed:
            raise Http404
        if form.is_valid():
            result = assistant.answer(user, form.cleaned_data["question"], current_language())
            if result.question is None:  # лимит: сообщение, вопрос не сохраняем
                messages.warning(request, result.answer)
                return redirect("immigration:page")
            return redirect(reverse("immigration:page") + f"#q-{result.question.pk}")
    reader = _reader(user)
    history = (Question.objects.filter(user=user).order_by("-created_at")[:HISTORY]
               if user.is_authenticated else [])
    return render(request, "immigration/page.html", {
        "conf": conf, "allowed": allowed, "form": form, "history": history, "reader": reader,
        "needs_region": allowed and isinstance(reader, Reader) and not reader.region,
        "region_form": RegionForm(), "login_form": LoginForm(), "email_ready": settings.EMAIL_CONFIGURED,
        "closed_beta": user.is_authenticated and not user.is_staff and not conf.enabled,
        "left_today": (max(conf.daily_questions - assistant.asked_today(user), 0)
                       if allowed and not user.is_staff else None),
        "lawyers_url": assistant.lawyers_page_url(), "eoir_url": assistant.EOIR_HELP_URL,
    })


@never_cache
def login_start(request):
    if not settings.EMAIL_CONFIGURED:
        messages.error(request, _("Вход для читателей пока не настроен. Загляните позже."))
        return redirect("immigration:page")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = accounts.normalize(form.cleaned_data["email"])
        if form.cleaned_data.get("company"):  # ловушка для ботов
            return redirect("immigration:login-code")
        if accounts.is_staff_email(email):
            # Сотрудники входят через админку. Отвечаем так же, как всем, — чтобы по форме нельзя было узнать,
            # какой адрес принадлежит сотруднику; письмо не отправляем.
            request.session[SESSION_EMAIL] = email
            return redirect("immigration:login-code")
        if accounts.too_many_codes(email, request):
            form.add_error(None, _("Слишком много запросов кода. Попробуйте через 15 минут."))
        else:
            try:
                accounts.send_code(email, request)
            except Exception:  # noqa: BLE001 — сбой почты не должен давать 500
                form.add_error(None, _("Не получилось отправить письмо. Попробуйте позже."))
            else:
                request.session[SESSION_EMAIL] = email
                request.session[SESSION_CONSENT] = True
                return redirect("immigration:login-code")
    return render(request, "immigration/login.html", {"form": form})


@never_cache
def login_code(request):
    email = request.session.get(SESSION_EMAIL)
    if not email:
        return redirect("immigration:login")
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if accounts.check_code(email, form.cleaned_data["code"]):
            user = accounts.reader_for(email, request, consent=bool(request.session.get(SESSION_CONSENT)))
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            request.session.pop(SESSION_EMAIL, None)
            request.session.pop(SESSION_CONSENT, None)
            return redirect("immigration:page")
        form.add_error("code", _("Код неверный или устарел. Запросите новый."))
    return render(request, "immigration/code.html", {"form": form, "email": email})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("immigration:page")


@require_POST
def set_region(request):
    reader = _reader(request.user)
    form = RegionForm(request.POST)
    if isinstance(reader, Reader) and form.is_valid():
        reader.region = form.cleaned_data["region"]
        reader.save(update_fields=["region"])
    return redirect("immigration:page")


@require_POST
def feedback(request, pk):
    if not request.user.is_authenticated:
        raise Http404
    question = get_object_or_404(Question, pk=pk, user=request.user)
    value = request.POST.get("value")
    if value in ("1", "-1"):
        question.feedback = int(value)
        question.save(update_fields=["feedback"])
    return redirect(reverse("immigration:page") + f"#q-{pk}")


@never_cache
def delete_account(request):
    """Читатель сам удаляет аккаунт: вместе с ним удаляются вопросы, ответы и согласие."""
    if not request.user.is_authenticated or request.user.is_staff:
        return redirect("immigration:page")
    if request.method == "POST" and request.POST.get("confirm") == "yes":
        user = request.user
        logout(request)
        user.delete()
        messages.success(request, _("Аккаунт и вся история вопросов удалены."))
        return redirect("immigration:page")
    return render(request, "immigration/delete.html")


@never_cache
@require_POST
def delete_history(request):
    if request.user.is_authenticated:
        Question.objects.filter(user=request.user).delete()
        messages.success(request, _("История вопросов удалена."))
    return redirect("immigration:page")
