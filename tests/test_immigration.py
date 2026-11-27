"""Иммиграционный помощник: доступ, жёсткие правила (личное, запрещённое), источники, лимиты, бюджет,
маскирование номеров, выключатель, согласие, вход по коду, база знаний. ИИ подменяется — в сеть тесты не ходят."""

import random
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from django.utils import timezone

from directory.models import Category, Listing
from immigration import assistant, knowledge
from immigration.extract import chunks, parse_html, parse_markdown
from immigration.models import CONSENT_VERSION, AssistantSettings, Chunk, LoginCode, Question, Reader, Source
from immigration.privacy import mask, purge_expired
from pipeline.models import AICall

pytestmark = pytest.mark.django_db
PAGE = "/immigration/"


# --- помощники ------------------------------------------------------------------------------------

class FakeAI:
    """Подмена ai.ask: разбор и ответ по заданным значениям, плюс запись вызовов (что ушло в модель)."""

    def __init__(self, category="general", language="ru", answer="Форму I-765 подают для разрешения на работу [1].",
                 cited=(1,), insufficient=False, cost=Decimal("0.0010")):
        self.category, self.language = category, language
        self.answer, self.cited, self.insufficient, self.cost = answer, list(cited), insufficient, cost
        self.calls = []

    def __call__(self, *, purpose, model, system, user, output, max_tokens=2000, **kw):
        self.calls.append({"purpose": purpose, "user": user, "system": system})
        AICall.objects.create(purpose=purpose, model=model, cost_usd=self.cost)
        if output is assistant.Triage:
            return assistant.Triage(category=self.category, language=self.language,
                                    query_en="employment authorization I-765", query_ru="разрешение на работу")
        return assistant.Draft(answer=self.answer, cited=self.cited, insufficient=self.insufficient)


@pytest.fixture
def fake_ai():
    fake = FakeAI()
    with mock.patch.object(assistant.ai, "ask", side_effect=fake):
        yield fake


@pytest.fixture
def kb():
    src = Source.objects.create(url="https://www.uscis.gov/i-765", title="I-765, Application for Employment "
                                "Authorization", agency=Source.Agency.USCIS, kind=Source.Kind.FORM,
                                checked_at=timezone.now(), fetched_at=timezone.now())
    Chunk.objects.create(source=src, section="Who May File Form I-765", position=0,
                         text="Certain noncitizens may file Form I-765 to request employment authorization and an "
                              "Employment Authorization Document (EAD).")
    return src


def reader(email="anna@example.com", consent=True, region=""):
    user = User.objects.create_user(username=f"r:{email}", email=email)
    Reader.objects.create(user=user, region=region, consent_at=timezone.now() if consent else None,
                          consent_version=CONSENT_VERSION if consent else "")
    return user


@pytest.fixture
def enabled():
    conf = AssistantSettings.load()
    conf.enabled = True
    conf.save()
    return conf


def ask(client, text):
    return client.post(PAGE, {"question": text})


# --- доступ и выключатель --------------------------------------------------------------------------

def test_anonymous_sees_login_and_cannot_ask(client, fake_ai):
    html = client.get(PAGE).content.decode()
    assert "Чего помощник не делает" in html and "Войти по e-mail" in html and 'name="question"' not in html
    assert ask(client, "Что такое форма I-765?").status_code == 404
    assert not fake_ai.calls and not Question.objects.exists()


def test_switch_off_only_staff(client, fake_ai, kb):
    user = reader()
    client.force_login(user)
    html = client.get(PAGE).content.decode()
    assert "закрытой проверке" in html and 'name="question"' not in html  # по умолчанию выключен
    assert ask(client, "Что такое форма I-765?").status_code == 404
    staff = User.objects.create_user("editor", password="x", is_staff=True)
    client.force_login(staff)
    assert ask(client, "Что такое форма I-765?").status_code == 302  # сотрудники — всегда
    conf = AssistantSettings.load()
    conf.enabled = True
    conf.save()
    client.force_login(user)
    assert ask(client, "Что такое форма I-765?").status_code == 302


def test_reader_has_no_access_to_admin_and_api(client, enabled):
    client.force_login(reader())
    assert client.get("/admin/").status_code == 302  # на страницу входа сотрудников
    assert client.get("/api/v1/articles/").status_code in (401, 403)


# --- жёсткие правила ------------------------------------------------------------------------------

def test_personal_question_refused_with_three_lawyers_and_eoir(client, enabled, kb):
    cat = Category.objects.get(slug="yuristy")
    Listing.objects.create(category=cat, name="Partner Immigration Law", description="Иммиграционный адвокат",
                           is_partner=True)
    fake = FakeAI(category="personal")
    client.force_login(reader(region="orlando"))
    with mock.patch.object(assistant.ai, "ask", side_effect=fake):
        ask(client, "Я приехал по parole в 2023 году, что мне лучше подавать?")
    q = Question.objects.get()
    assert q.kind == Question.Kind.PERSONAL and "не отвечаю на вопросы о вашей личной ситуации" in q.answer
    lawyers = [x for x in q.lawyers if not x.get("external")]
    assert len(lawyers) == 3 and lawyers[0]["name"] == "Partner Immigration Law"  # партнёр первым
    assert q.lawyers[-1]["url"] == "https://www.justice.gov/eoir/find-legal-representation"
    assert [c["purpose"] for c in fake.calls] == [AICall.Purpose.IMMIGRATION_TRIAGE]  # до генерации не дошло
    html = client.get(PAGE).content.decode()
    assert "Partner Immigration Law" in html and "justice.gov/eoir/find-legal-representation" in html


@pytest.mark.parametrize("text,kind", [
    ("Есть ли у меня шансы получить грин-карту через брак?", "personal"),
    ("Успею ли я подать на продление TPS до конца срока?", "personal"),
    ("Что будет, если я не отмечусь в ICE?", "personal"),
    ("Чи є у мене шанси на притулок?", "personal"),
    ("Как обмануть офицера на интервью по браку?", "prohibited"),
    ("Как спрятаться от ICE, чтобы не нашли?", "prohibited"),
    ("Заполните за меня I-589, вот мои данные", "prohibited"),
    ("Что сказать на интервью, чтобы одобрили?", "prohibited"),
])
def test_rules_override_model_even_if_it_says_general(client, enabled, kb, text, kind):
    fake = FakeAI(category="general")  # модель ошиблась — жёсткое правило всё равно отказывает
    client.force_login(reader())
    with mock.patch.object(assistant.ai, "ask", side_effect=fake):
        ask(client, text)
    q = Question.objects.get()
    assert q.kind == kind and not q.sources
    assert AICall.Purpose.IMMIGRATION_ANSWER not in [c["purpose"] for c in fake.calls]


def test_prohibited_by_model_is_refused(client, enabled, kb):
    fake = FakeAI(category="prohibited")
    client.force_login(reader())
    with mock.patch.object(assistant.ai, "ask", side_effect=fake):
        ask(client, "Как сделать, чтобы брак выглядел настоящим для USCIS?")
    assert Question.objects.get().kind == Question.Kind.PROHIBITED


# --- источники ------------------------------------------------------------------------------------

def test_answer_has_sources_and_disclaimer(client, enabled, kb, fake_ai):
    client.force_login(reader())
    resp = ask(client, "Что такое форма I-765 и кто её подаёт?")
    q = Question.objects.get()
    assert resp.status_code == 302 and resp["Location"] == f"{PAGE}#q-{q.pk}"
    assert q.kind == Question.Kind.ANSWERED and q.sources[0]["url"] == "https://www.uscis.gov/i-765"
    assert q.sources[0]["checked"] == timezone.localtime(kb.checked_at).strftime("%d.%m.%Y") or q.sources[0]["checked"]
    prompt = fake_ai.calls[-1]["user"]
    assert "Who May File Form I-765" in prompt and "[1] I-765" in prompt  # в модель — только найденные фрагменты
    html = client.get(PAGE).content.decode()
    assert f'href="#q{q.pk}-s1"' in html and "проверено" in html
    assert "Это общая информация, а не юридическая консультация" in html and 'href="/links/yuristy/"' in html


def test_no_fragments_means_not_in_base(client, enabled, fake_ai):
    client.force_login(reader())
    ask(client, "Что такое форма I-765?")  # база пустая
    q = Question.objects.get()
    assert q.kind == Question.Kind.NO_SOURCES and "В моей базе этого нет" in q.answer and not q.sources
    assert AICall.Purpose.IMMIGRATION_ANSWER not in [c["purpose"] for c in fake_ai.calls]


@pytest.mark.parametrize("answer,cited,insufficient", [
    ("Пошлина составляет $520 [7].", [7], False),  # сноска на несуществующий источник
    ("Пошлина составляет $520.", [], False),  # без сносок
    ("В источниках этого нет.", [], True),
    ("Во фрагментах нет информации об этом: они про смену адреса [1].", [1], True),  # сноски не по вопросу
])
def test_answer_without_real_citations_becomes_not_in_base(client, enabled, kb, answer, cited, insufficient):
    fake = FakeAI(answer=answer, cited=cited, insufficient=insufficient)
    client.force_login(reader())
    with mock.patch.object(assistant.ai, "ask", side_effect=fake):
        ask(client, "Сколько стоит подать I-765?")
    q = Question.objects.get()
    assert q.kind == Question.Kind.NO_SOURCES and "$520" not in q.answer and "смену адреса" not in q.answer


def test_partial_answer_with_real_citations_is_kept(client, enabled, kb):
    fake = FakeAI(answer="Точной суммы в базе нет. Размер пошлины публикуется в Fee Schedule [1].", cited=[1],
                  insufficient=True)
    client.force_login(reader())
    with mock.patch.object(assistant.ai, "ask", side_effect=fake):
        ask(client, "Сколько стоит подать I-765?")
    q = Question.objects.get()
    assert q.kind == Question.Kind.ANSWERED and "Fee Schedule [1]" in q.answer and q.sources


def test_answer_in_ukrainian(client, enabled, kb):
    fake = FakeAI(category="personal", language="uk")
    client.force_login(reader())
    with mock.patch.object(assistant.ai, "ask", side_effect=fake):
        client.post("/uk/immigration/", {"question": "Що мені подавати після parole?"})
    q = Question.objects.get()
    assert q.language == "uk" and "Я не відповідаю на питання про вашу особисту ситуацію" in q.answer


# --- лимиты и бюджет ------------------------------------------------------------------------------

def test_daily_limit(client, enabled, kb, fake_ai):
    enabled.daily_questions = 2
    enabled.save()
    client.force_login(reader())
    for _ in range(2):
        ask(client, "Что такое форма I-765?")
    calls = len(fake_ai.calls)
    resp = ask(client, "Что такое форма I-130?")
    assert resp.status_code == 302 and Question.objects.count() == 2 and len(fake_ai.calls) == calls
    assert "лимит вопросов исчерпан" in client.get(PAGE).content.decode()


def test_monthly_budget_fuse(client, enabled, kb, fake_ai):
    enabled.monthly_budget_usd = Decimal("1.00")
    enabled.save()
    AICall.objects.create(purpose=AICall.Purpose.IMMIGRATION_ANSWER, model="deepseek-flash", cost_usd=Decimal("1.0"))
    AICall.objects.create(purpose=AICall.Purpose.WRITE, model="x", cost_usd=Decimal("50"))  # новости не в счёт
    client.force_login(reader())
    ask(client, "Что такое форма I-765?")
    assert not fake_ai.calls and not Question.objects.exists()
    assert "исчерпан месячный лимит" in client.get(PAGE).content.decode()


def test_question_length_limit(client, enabled, kb, fake_ai):
    enabled.max_question_chars = 50
    enabled.save()
    client.force_login(reader())
    resp = ask(client, "Что такое форма I-765? " * 10)
    assert resp.status_code == 200 and not Question.objects.exists() and not fake_ai.calls


# --- приватность ----------------------------------------------------------------------------------

def test_masking_numbers_before_saving_and_before_model(client, enabled, kb, fake_ai):
    client.force_login(reader())
    ask(client, "Мой A-number A123456789, дело IOE0912345678, SSN 123-45-6789 — что такое I-765?")
    q = Question.objects.get()
    for secret in ("123456789", "IOE0912345678", "123-45-6789"):
        assert secret not in q.question
        assert all(secret not in c["user"] for c in fake_ai.calls)
    assert "[A-номер скрыт]" in q.question and "[номер дела скрыт]" in q.question and "[SSN скрыт]" in q.question


@pytest.mark.parametrize("raw,masked", [
    ("A12345678", "[A-номер скрыт]"), ("A-123-456-789", "[A-номер скрыт]"), ("a 123456789", "[A-номер скрыт]"),
    ("EAC2190012345", "[номер дела скрыт]"), ("msc 2190012345", "[номер дела скрыт]"),
    ("123 45 6789", "[SSN скрыт]"), ("987654321", "[SSN скрыт]"),
])
def test_mask_patterns(raw, masked):
    assert mask(f"номер {raw} тут") == f"номер {masked} тут"
    assert mask("Форма I-765 и N-400, пошлина $520, 2026 год") == "Форма I-765 и N-400, пошлина $520, 2026 год"


def test_retention_purge():
    user = reader()
    old = Question.objects.create(user=user, question="старый", kind="answered")
    Question.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=31))
    fresh = Question.objects.create(user=user, question="новый", kind="answered")
    assert purge_expired() == 1 and list(Question.objects.all()) == [fresh]


# --- регистрация, согласие, удаление --------------------------------------------------------------

def test_login_by_code_saves_consent(client):
    resp = client.post("/immigration/vhod/", {"email": "Anna@Example.com"})
    assert resp.status_code == 200 and not mail.outbox  # без галочки согласия кода нет
    resp = client.post("/immigration/vhod/", {"email": "Anna@Example.com", "consent": "on"},
                       HTTP_CF_CONNECTING_IP="203.0.113.7")
    assert resp.status_code == 302 and len(mail.outbox) == 1
    code = next(w for w in mail.outbox[0].subject.split() if w.isdigit())
    assert code not in LoginCode.objects.get().code_hash  # храним только хэш
    assert client.post("/immigration/vhod/kod/", {"code": "000000" if code != "000000" else "111111"}).status_code == 200
    resp = client.post("/immigration/vhod/kod/", {"code": code}, HTTP_CF_CONNECTING_IP="203.0.113.7")
    assert resp.status_code == 302
    user = User.objects.get(email="anna@example.com")
    assert user.username == "r:anna@example.com" and not user.is_staff and not user.has_usable_password()
    r = user.reader
    assert r.consent_at and r.consent_version == CONSENT_VERSION and r.consent_ip == "203.0.113.7"
    assert client.post("/immigration/vhod/kod/", {"code": code}).status_code == 302  # код одноразовый → снова вход


def test_staff_email_cannot_log_in_by_code(client):
    User.objects.create_user("boss", email="boss@example.com", password="x", is_staff=True)
    resp = client.post("/immigration/vhod/", {"email": "boss@example.com", "consent": "on"})
    assert resp.status_code == 302 and resp["Location"] == "/immigration/vhod/kod/"  # как для всех
    assert not mail.outbox and not LoginCode.objects.exists()


@override_settings(EMAIL_CONFIGURED=False)
def test_login_disabled_without_mail(client):
    assert client.get("/immigration/vhod/").status_code == 302
    assert "Вход для читателей скоро откроется" in client.get(PAGE).content.decode()


def test_code_attempts_limited(client):
    client.post("/immigration/vhod/", {"email": "x@example.com", "consent": "on"})
    code = next(w for w in mail.outbox[0].subject.split() if w.isdigit())
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(LoginCode.MAX_ATTEMPTS):
        client.post("/immigration/vhod/kod/", {"code": wrong})
    client.post("/immigration/vhod/kod/", {"code": code})
    assert not User.objects.filter(email="x@example.com").exists()  # после 5 ошибок код сгорел


def test_delete_account_and_history(client, enabled, kb, fake_ai):
    user = reader()
    client.force_login(user)
    ask(client, "Что такое форма I-765?")
    client.post("/immigration/akkaunt/udalit/", {"confirm": "yes"})
    assert not User.objects.filter(pk=user.pk).exists() and not Question.objects.exists()
    assert not Reader.objects.exists()


def test_feedback_only_own_question(client, enabled, kb, fake_ai):
    user = reader()
    client.force_login(user)
    ask(client, "Что такое форма I-765?")
    q = Question.objects.get()
    client.post(f"/immigration/otvet/{q.pk}/ocenka/", {"value": "-1"})
    q.refresh_from_db()
    assert q.feedback == -1
    client.force_login(reader("other@example.com"))
    assert client.post(f"/immigration/otvet/{q.pk}/ocenka/", {"value": "1"}).status_code == 404


def test_region_asked_once(client, enabled):
    user = reader()
    client.force_login(user)
    assert 'name="region"' in client.get(PAGE).content.decode()
    client.post("/immigration/region/", {"region": "tampa"})
    assert Reader.objects.get(user=user).region == "tampa"
    assert 'name="region"' not in client.get(PAGE).content.decode()


def test_ukrainian_page(client):
    html = client.get("/uk/immigration/").content.decode()
    assert "Імміграційний помічник" in html and "Чого помічник не робить" in html


def test_lawyers_order_partner_region_random():
    cat = Category.objects.get(slug="yuristy")
    Listing.objects.filter(category=cat).update(is_active=False)
    from news.models import Region

    tampa, miami = Region.objects.get(slug="tampa"), Region.objects.get(slug="miami")
    Listing.objects.create(category=cat, name="P", description="immigration", is_partner=True, region=miami)
    Listing.objects.create(category=cat, name="T", description="Иммиграционный юрист", region=tampa)
    for n in range(5):
        Listing.objects.create(category=cat, name=f"M{n}", description="иммиграция", region=miami)
    Listing.objects.create(category=cat, name="Family", description="семейное право", region=tampa)
    names = [x["name"] for x in assistant.pick_lawyers("tampa", rng=random.Random(1))]
    assert names[:2] == ["P", "T"] and names[2].startswith("M") and "Family" not in names


# --- база знаний ----------------------------------------------------------------------------------

HTML = """<html><head><title>I-765, Application for Employment Authorization | USCIS</title></head><body>
<nav><a>Menu item</a></nav><main><h1>I-765, Application for Employment Authorization</h1>
<p>Certain noncitizens who are in the United States may file Form I-765 to request employment authorization
and an Employment Authorization Document. Other noncitizens whose immigration status authorizes them to work
in the United States without restrictions may also use Form I-765 to apply for an EAD that shows such
authorization.</p><h2>Filing Fee</h2><p>See the Fee Schedule G-1055 for the current fee. Fees may change and
you should always verify the amount before filing your application with USCIS online or by mail.</p>
<h2>Forms and Documents</h2><p>Form I-765 instructions explain who is eligible, what evidence to submit,
where to file, how to pay the fee, and what happens after you file. Read them carefully before filing.</p>
<script>var x = 1;</script></main><footer>Footer text</footer></body></html>"""


def test_parse_html_sections_and_chunks():
    page = parse_html(HTML)
    assert page.title == "I-765, Application for Employment Authorization"
    assert [s.heading for s in page.sections][:2] == ["I-765, Application for Employment Authorization", "Filing Fee"]
    assert "Menu item" not in page.text and "Footer text" not in page.text and "var x" not in page.text
    parts = chunks(page)
    assert parts and all(len(text.split()) >= 8 for _h, text in parts)
    md = parse_markdown("Вступление про грин-карту.\n\n## Пошлина\n\nI-90 стоит **$415** онлайн.", "Гайд")
    assert [s.heading for s in md.sections] == ["", "Пошлина"] and "**" not in md.text


class FakeHTTP:
    def __init__(self, routes):
        self.routes, self.final = routes, {}

    def get(self, url, **kw):
        status, body = self.routes[url]
        return SimpleNamespace(status_code=status, text=body, url=self.final.get(url, url), ok=status < 400,
                               json=lambda: body, raise_for_status=lambda: None, headers={})


def test_fetch_official_statuses_and_change_detection():
    O, K = knowledge.S.Official, Source.Kind
    ok = O("https://www.uscis.gov/i-765", Source.Agency.USCIS, K.FORM)
    http = FakeHTTP({
        ok.url: (200, HTML),
        "https://www.uscis.gov/i-485": (403, "Access Denied"),
        "https://www.uscis.gov/i-130": (404, "Not found"),
        "https://www.uscis.gov/i-90": (200, "<html><body><div id='app'>Please enable JavaScript</div></body></html>"),
        "https://www.uscis.gov/ukraine": (200, HTML),
    })
    first = knowledge.fetch_official(ok, http)
    assert first.status == "ok" and first.changed and first.chunks >= 2
    again = knowledge.fetch_official(ok, http)
    assert again.status == "ok" and not again.changed  # тот же текст — не перенарезаем
    http.routes[ok.url] = (200, HTML.replace("Fees may change", "Fees changed on November 1"))
    assert knowledge.fetch_official(ok, http).changed and Source.objects.get(url=ok.url).changed_at
    assert knowledge.fetch_official(O("https://www.uscis.gov/i-485", "uscis", K.FORM), http).status == "blocked"
    assert knowledge.fetch_official(O("https://www.uscis.gov/i-130", "uscis", K.FORM), http).status == "not_found"
    assert knowledge.fetch_official(O("https://www.uscis.gov/i-90", "uscis", K.FORM), http).status == "js_only"
    # переадресация: страница хранится под конечным адресом, без дубля под старым
    http.routes["https://www.uscis.gov/ukraine"] = (200, HTML)
    http.final = {"https://www.uscis.gov/ukraine": "https://www.uscis.gov/newsroom/alerts/update-on-form-i-134a"}
    moved = knowledge.fetch_official(O("https://www.uscis.gov/ukraine", "uscis", K.PAGE), http)
    assert moved.url == "https://www.uscis.gov/newsroom/alerts/update-on-form-i-134a" and "переадресация" in moved.note
    assert not Source.objects.filter(url="https://www.uscis.gov/ukraine").exists()
    bad = knowledge.fetch_official(O("https://evil.example.com/i-765", "uscis", K.FORM), http)
    assert bad.status == "failed" and not Source.objects.filter(url__contains="evil").exists()


def test_federal_register_skips_information_collections():
    docs = {"results": [
        {"title": "Extension of the Designation of Ukraine for Temporary Protected Status", "type": "Notice",
         "abstract": "This notice extends the designation of Ukraine for TPS for 18 months.",
         "html_url": "https://www.federalregister.gov/documents/2026/10/01/2026-1/ukraine-tps",
         "publication_date": "2026-10-01", "raw_text_url": ""},
        {"title": "Agency Information Collection Activities; New Collection", "type": "Notice", "abstract": "OMB",
         "html_url": "https://www.federalregister.gov/documents/2026/10/02/2026-2/x", "publication_date": "2026-10-02",
         "raw_text_url": ""},
    ]}
    http = FakeHTTP({knowledge.S.FR_API: (200, docs)})
    report = knowledge.Report()
    knowledge.update_federal_register(http, report)
    titles = list(Source.objects.values_list("title", flat=True))
    assert titles == ["Notice: Extension of the Designation of Ukraine for Temporary Protected Status"]
    assert Source.objects.get().published_on.isoformat() == "2026-10-01"


def test_our_guides_and_news_indexed():
    from guides.models import Guide
    from news.models import Article

    Guide.objects.create(title="Грин-карта", slug="grin-karta", status=Guide.Status.PUBLISHED,
                         published_at=timezone.now(), body="Вступление.\n\n## Замена карты\n\nКарту меняют по "
                         "форме I-90, пошлина указана в таблице G-1055 и может меняться каждый год.")
    Article.objects.create(title="USCIS продлил TPS для Украины", teaser="Продление на 18 месяцев",
                           body="Министерство внутренней безопасности продлило TPS для граждан Украины на 18 "
                                "месяцев, разрешения на работу продлены автоматически.",
                           status=Article.Status.PUBLISHED, published_at=timezone.now())
    report = knowledge.Report()
    knowledge.update_ours(report)
    kinds = set(Source.objects.values_list("kind", "language"))
    assert {("guide", "ru"), ("article", "ru")} <= kinds and Chunk.objects.count() >= 2


def test_search_finds_relevant_chunk(kb):
    from immigration.search import search

    hits = search("employment authorization I-765", "разрешение на работу")
    assert hits and hits[0].chunk.source == kb
    assert search("naturalization civics test", "экзамен на гражданство") == []


def test_answer_html_lists_and_citations():
    from immigration.templatetags.immigration_tags import answer_html

    q = Question(pk=7, answer="Форма AR-11 — уведомление [1].\nКогда подают:\n- в течение 10 дней [1]\n- онлайн [2]"
                             "\n\n<script>alert(1)</script> **важно**")
    html = answer_html(q)
    assert "<p>Форма AR-11" in html and "<ul><li>в течение 10 дней" in html and html.count("<li>") == 2
    assert 'href="#q7-s2"' in html and "<script>" not in html and "<b>важно</b>" in html


def test_admin_dashboard_and_switch(client, kb):
    admin_user = User.objects.create_superuser("root", "root@example.com", "x")
    client.force_login(admin_user)
    user = reader()
    Question.objects.create(user=user, question="вопрос", kind="answered", feedback=-1)
    AICall.objects.create(purpose=AICall.Purpose.IMMIGRATION_ANSWER, model="deepseek-flash", cost_usd=Decimal("0.25"))
    html = client.get("/admin/immigration/question/").content.decode()
    assert "Расход:" in html and "$0,25" in html and "👎 не разобрано:</b> <a" in html
    assert "только сотрудники (закрытая проверка)" in html and "источников 1" in html
    assert client.get("/admin/immigration/source/?fresh=stale").status_code == 200
    assert client.get("/admin/immigration/assistantsettings/").status_code == 200


def test_policy_manual_updates_section_not_indexed():
    page = parse_html("<main><h2>A. Continuous Residence</h2><p>" + "residence rule text " * 20 + "</p>"
                      "<h2>Updates</h2><p>" + "technical update fee federal register " * 20 + "</p></main>")
    assert [h for h, _t in chunks(page)] == ["A. Continuous Residence"]


def test_api_update_and_sources_staff_only(client, kb, tmp_path, monkeypatch):
    from rest_framework.authtoken.models import Token

    from immigration import api

    monkeypatch.setattr(api, "LOCK", tmp_path / "lock")
    staff = User.objects.create_user("agent", is_staff=True)
    auth = {"HTTP_AUTHORIZATION": f"Token {Token.objects.create(user=staff).key}"}
    client.force_login(reader())
    assert client.post("/api/v1/immigration/update/").status_code in (401, 403)  # читатель — нет
    client.logout()
    with mock.patch.object(api.subprocess, "Popen") as popen:
        popen.return_value.wait.return_value = 0
        assert client.post("/api/v1/immigration/update/", **auth).status_code == 202
        args = popen.call_args.args[0]
        assert args[-2:] == ["manage.py", "immigration_update"]
    data = client.get("/api/v1/immigration/sources/", **auth).json()
    assert data["sources_ok"] == 1 and data["chunks"] == 1 and data["sources"][0]["url"] == kb.url
