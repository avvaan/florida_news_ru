// Переключатель «UA | RU»: запоминаем выбор на год — он важнее языка браузера (core.middleware.PreferredLanguageMiddleware).
document.addEventListener("click", function (e) {
  var link = e.target.closest && e.target.closest(".lang__item");
  if (link && link.lang) {
    document.cookie = "lang=" + link.lang + "; path=/; max-age=31536000; samesite=lax";
  }
});
