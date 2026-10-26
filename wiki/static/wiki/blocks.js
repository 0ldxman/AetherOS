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

    function initMap(frame) {
        frame.closest(".widget--map").dataset.mode = live ? "live" : "still";
        frame.src = live ? frame.dataset.live : frame.dataset.static;
    }

    document.querySelectorAll(".widget--gallery").forEach(initGallery);
    document.querySelectorAll(".map-embed").forEach(initMap);
})();
