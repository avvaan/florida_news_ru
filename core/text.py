"""Мелкие текстовые утилиты: транслитерация для slug и нормализация заголовков."""

import re
import unicodedata

# Упрощённая транслитерация (близко к Яндексу/ГОСТ 7.79 «Б»), удобная для URL.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
    # украинские буквы
    "є": "ye", "і": "i", "ї": "yi", "ґ": "g",
}


def transliterate(text: str) -> str:
    out = []
    for ch in text.lower():
        out.append(_TRANSLIT.get(ch, ch))
    return "".join(out)


def make_slug(text: str, max_length: int = 90) -> str:
    """«Ураган «Милтон» идёт на Тампу» -> "uragan-milton-idyot-na-tampu"."""
    value = transliterate(text)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    if len(value) > max_length:
        value = value[:max_length].rsplit("-", 1)[0]
    return value


_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "for", "with", "by",
    "from", "as", "is", "are", "was", "were", "be", "been", "it", "its", "this", "that",
    "after", "before", "over", "into", "about", "amid", "says", "said", "new", "news", "how",
    "what", "why", "who", "will", "can", "could", "may", "has", "have", "had", "not", "no",
    "up", "out", "more", "than", "you", "your", "here", "s", "video", "watch", "live",
    "update", "updates", "florida", "fl",
}


def title_tokens(title: str) -> set[str]:
    """Набор значимых токенов заголовка для сравнения похожести.

    Грубый стемминг (первые 6 символов) склеивает evacuate/evacuation/evacuations.
    """
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w[:6] for w in words if w not in _STOPWORDS and (len(w) > 2 or w.isdigit())}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
