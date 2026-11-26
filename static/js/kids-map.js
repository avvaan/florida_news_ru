/* Карта каталога «Детям». Leaflet и тайлы OpenStreetMap загружаются только по кнопке «Показать на карте»:
   страница без карты не тянет ни скриптов, ни запросов к сторонним серверам. */
(function () {
  "use strict";
  var button = document.querySelector("[data-kids-map]");
  var box = document.getElementById("kids-map");
  var data = document.getElementById("kids-points");
  if (!button || !box || !data) return;
  var points = JSON.parse(data.textContent || "[]");
  var map = null;

  function load(tag, attrs) {
    return new Promise(function (resolve, reject) {
      var el = document.createElement(tag);
      Object.keys(attrs).forEach(function (k) { el[k] = attrs[k]; });
      el.onload = resolve;
      el.onerror = reject;
      document.head.appendChild(el);
    });
  }

  function popup(p) {
    var wrap = document.createElement("div");
    var link = document.createElement("a");
    link.href = p.url;
    link.textContent = p.name;
    wrap.appendChild(link);
    if (p.city) {
      var city = document.createElement("div");
      city.textContent = p.city + (p.exact ? "" : " · " + (button.dataset.approx || ""));
      wrap.appendChild(city);
    }
    return wrap;
  }

  function draw() {
    var L = window.L;
    map = L.map(box, { scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(map);
    var bounds = [];
    points.forEach(function (p) {
      L.circleMarker([p.lat, p.lng], {
        radius: 8, weight: 2, color: "#07524f", fillColor: p.exact ? "#0b7a75" : "#7fd1c7", fillOpacity: 0.9
      }).bindPopup(popup(p)).addTo(map);
      bounds.push([p.lat, p.lng]);
    });
    if (bounds.length === 1) map.setView(bounds[0], 13);
    else map.fitBounds(bounds, { padding: [24, 24], maxZoom: 13 });
  }

  button.addEventListener("click", function () {
    var open = box.hidden;
    box.hidden = !open;
    var note = box.parentNode.querySelector(".kids-map__note");
    if (note) note.hidden = !open || points.every(function (p) { return p.exact; });
    button.setAttribute("aria-expanded", String(open));
    if (!open) return;
    if (map) { map.invalidateSize(); return; }
    button.disabled = true;
    Promise.all([
      load("link", { rel: "stylesheet", href: button.dataset.css }),
      window.L ? Promise.resolve() : load("script", { src: button.dataset.js })
    ]).then(draw).catch(function () {
      box.textContent = button.dataset.error || "";
    }).then(function () { button.disabled = false; });
  });
})();
