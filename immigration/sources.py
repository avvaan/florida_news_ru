"""Разрешённые официальные источники базы знаний. Скачиваем ТОЛЬКО отсюда (и из Federal Register API).

Добавляя адрес, проверьте его вживую: `python manage.py immigration_update --only <адрес>`. Страницы, которые
сайт не отдаёт (403), которых нет (404) или которые собираются JavaScript, команда пометит и пропустит.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Source

A, K = Source.Agency, Source.Kind


@dataclass(frozen=True)
class Official:
    url: str
    agency: str
    kind: str
    title: str = ""


USCIS = "https://www.uscis.gov"

FORMS = {
    "i-765": "I-765, Application for Employment Authorization",
    "i-485": "I-485, Application to Register Permanent Residence or Adjust Status",
    "i-130": "I-130, Petition for Alien Relative",
    "i-131": "I-131, Application for Travel Documents, Parole Documents, and Arrival/Departure Records",
    "i-90": "I-90, Application to Replace Permanent Resident Card",
    "n-400": "N-400, Application for Naturalization",
    "i-821": "I-821, Application for Temporary Protected Status",
    "i-589": "I-589, Application for Asylum and for Withholding of Removal",
    "ar-11": "AR-11, Alien's Change of Address Card",
    "i-751": "I-751, Petition to Remove Conditions on Residence",
    "i-864": "I-864, Affidavit of Support",
    "i-134a": "I-134A, Online Request to be a Supporter",
    "i-539": "I-539, Application to Extend/Change Nonimmigrant Status",
    "i-912": "I-912, Request for Fee Waiver",
    "n-600": "N-600, Application for Certificate of Citizenship",
    "i-131a": "I-131A, Application for Carrier Documentation",
    "g-1055": "G-1055, Fee Schedule",
}

POLICY_MANUAL = [
    "volume-12-part-d-chapter-3",  # непрерывное проживание (гражданство)
    "volume-12-part-d-chapter-4",  # физическое присутствие
    "volume-12-part-e-chapter-2",  # экзамен по английскому и истории
    "volume-12-part-f-chapter-2",  # моральный облик
    "volume-12-part-f-chapter-5",  # условные основания для отказа
]

PAGES = [
    ("/forms/filing-fees", K.FEES, "Filing Fees"),
    ("/humanitarian/temporary-protected-status", K.PAGE, "Temporary Protected Status"),
    ("/humanitarian/humanitarian-parole", K.PAGE, "Humanitarian or Significant Public Benefit Parole"),
    ("/ukraine", K.PAGE, "Information for Ukrainians"),
    ("/humanitarian/uniting-for-ukraine", K.PAGE, "Uniting for Ukraine"),
    ("/newsroom/alerts", K.NEWS, "USCIS Newsroom: Alerts"),
    ("/addresschange", K.PAGE, "How to Change Your Address"),
    ("/alienregistration", K.PAGE, "Alien Registration Requirement"),
    ("/green-card/after-we-grant-your-green-card/replace-your-green-card", K.PAGE, "Replace Your Green Card"),
    ("/green-card/after-we-grant-your-green-card/international-travel-as-a-permanent-resident", K.PAGE,
     "International Travel as a Permanent Resident"),
    ("/green-card/after-we-grant-your-green-card/conditional-permanent-residence/"
     "removing-conditions-on-permanent-residence-based-on-marriage", K.PAGE,
     "Removing Conditions on Permanent Residence Based on Marriage"),
    ("/citizenship/find-study-materials-and-resources/study-for-the-test", K.PAGE, "Study for the Test"),
    ("/citizenship/exceptions-and-accommodations", K.PAGE, "Exceptions and Accommodations"),
    ("/scams-fraud-and-misconduct/avoid-scams/common-scams", K.PAGE, "Common Scams"),
    ("/forms/filing-guidance/tips-for-filing-forms-by-mail", K.PAGE, "Tips for Filing Forms by Mail"),
]

VISA_BULLETIN_INDEX = "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html"

EOIR = [
    ("https://www.justice.gov/eoir/find-legal-representation", "Find Legal Representation"),
    ("https://www.justice.gov/eoir/list-pro-bono-legal-service-providers", "List of Pro Bono Legal Service Providers"),
    ("https://www.justice.gov/eoir/recognition-accreditation-roster-reports",
     "Recognized Organizations and Accredited Representatives Roster"),
    ("https://www.justice.gov/eoir/self-help-materials", "Self-Help Materials"),
]

# Federal Register API: документы этих ведомств за последние FR_DAYS дней.
FR_API = "https://www.federalregister.gov/api/v1/documents.json"
FR_AGENCIES = ["u-s-citizenship-and-immigration-services", "executive-office-for-immigration-review",
               "u-s-immigration-and-customs-enforcement"]
FR_DAYS = 90
# анкеты для OMB (Paperwork Reduction Act): правил в них нет
FR_SKIP_TITLES = ("Agency Information Collection Activities", "Extension Without Change of a Currently Approved")
FR_MAX_WORDS = 3000  # от длинного документа берём начало: суть, сроки, кого касается

# Наши гайды по иммиграции (только опубликованные) и заметки за последние 90 дней.
OUR_GUIDES = ["grazhdanstvo-ssha", "grin-karta", "smena-adresa", "ssn-i-itin", "moshennichestvo",
              "perevod-notarius-apostil"]
NEWS_DAYS = 90

ALLOWED_HOSTS = ("www.uscis.gov", "travel.state.gov", "www.justice.gov", "www.federalregister.gov")


def officials() -> list[Official]:
    out = [Official(f"{USCIS}/{slug}", A.USCIS, K.FEES if slug == "g-1055" else K.FORM, title)
           for slug, title in FORMS.items()]
    out += [Official(f"{USCIS}/policy-manual/{chapter}", A.USCIS, K.POLICY) for chapter in POLICY_MANUAL]
    out += [Official(f"{USCIS}{path}", A.USCIS, kind, title) for path, kind, title in PAGES]
    out += [Official(url, A.EOIR, K.PAGE, title) for url, title in EOIR]
    return out


def is_allowed(url: str) -> bool:
    host = url.split("://", 1)[-1].split("/", 1)[0].lower()
    return url.startswith("https://") and host in ALLOWED_HOSTS
