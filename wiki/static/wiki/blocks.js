/*
 * Составные виджеты документа: галерея и карта.
 *
 * Вид зависит от страницы: у web, rec и инфобокса галерея это карусель, а карта живая;
 * у doc и scan галерея это плитка, а карта неподвижный кадр.
 */
(function () {
    "use strict";

    const body = document.body;
    const live = ["doc--web", "doc--rec", "doc--infobox"].some(name => body.classList.contains(name));
    const mode = live ? "carousel" : "tile";

    function initGallery(box) {
        box.dataset.mode = mode;

        if (!live) {
            return;
        }

        const items = Array.from(box.querySelectorAll(".gallery-item"));
        const count = box.querySelector(".gallery-count");
        let index = 0;

        function show(next) {
            index = (next + items.length) % items.length;
            items.forEach((item, i) => item.classList.toggle("is-active", i === index));

            if (count) {
                count.textContent = `${index + 1} / ${items.length}`;
            }
        }

        box.querySelector(".gallery-prev").addEventListener("click", () => show(index - 1));
        box.querySelector(".gallery-next").addEventListener("click", () => show(index + 1));
        box.addEventListener("keydown", function (event) {
            if (event.key === "ArrowLeft") {
                show(index - 1);
            } else if (event.key === "ArrowRight") {
                show(index + 1);
            }
        });

        show(0);
    }

    // светлые страницы получают карту на бумаге, тёмные терминальную
    const dark = body.classList.contains("doc--rec") || body.classList.contains("doc--infobox") ||
        (body.classList.contains("doc--web") && document.querySelector(".site-preset--dark"));
    const theme = dark ? "term" : "print";

    function initMap(frame) {
        const widget = frame.closest(".widget--map");
        widget.dataset.mode = live ? "live" : "still";
        widget.dataset.theme = theme;

        const src = live ? frame.dataset.live : frame.dataset.static;
        const at = src.indexOf("#");
        frame.src = (at < 0 ? src : src.slice(0, at)) + "&theme=" + theme + (at < 0 ? "" : src.slice(at));
    }

    // масштаб и координаты в подписи следуют за видом карты
    const NICE_KM = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];

    function coord(value, plus, minus) {
        return Math.abs(value).toFixed(2) + "°" + (value >= 0 ? plus : minus);
    }

    function updateView(widget, view) {
        const status = widget.querySelector(".map-status");
        if (status) {
            status.textContent = coord(view.lat, "N", "S") + " " + coord(view.lon, "E", "W") +
                " · ×" + view.zoom.toFixed(1);
        }

        // километров на пиксель (плитки по 512 px), полоса масштаба около четверти ширины кадра
        const kmPerPx = 78271.52 * Math.cos(view.lat * Math.PI / 180) / Math.pow(2, view.zoom) / 1000;
        const target = kmPerPx * Math.max(view.width, 200) * 0.22;
        const km = NICE_KM.reduce((best, item) => Math.abs(item - target) < Math.abs(best - target) ? item : best);
        const bar = widget.querySelector(".map-scale-bar");
        const text = widget.querySelector(".map-scale-text");

        if (bar) {
            bar.style.width = (km / kmPerPx / Math.max(view.width, 1) * 100).toFixed(1) + "%";
        }

        if (text) {
            text.textContent = km + " км";
        }
    }

    window.addEventListener("message", function (event) {
        if (event.origin !== window.location.origin || !event.data || event.data.type !== "aether-map-view") {
            return;
        }

        document.querySelectorAll(".map-embed").forEach(function (frame) {
            if (frame.contentWindow === event.source) {
                updateView(frame.closest(".widget--map"), event.data);
            }
        });
    });

    document.querySelectorAll(".widget--gallery").forEach(initGallery);
    document.querySelectorAll(".map-embed").forEach(initMap);
})();
