/* =========================================================
   AETHER.OS BOOT
   Загрузка машины это консольная сцена (desktop/boots.py).
   Здесь только выбор между полной и короткой версией и переход
   на экран входа.

   Повторный заход в рамках вкладки: короткая загрузка, вдвое
   быстрее. ?boot=full в адресе включает полную.
   ========================================================= */

(function () {
    "use strict";

    const SCENES = JSON.parse(document.getElementById("boot-config").textContent).scenes;
    const SEEN_KEY = "aether_boot_seen";

    function storage(action) {
        try { return action(window.sessionStorage); } catch (error) { return null; }   // может быть недоступно
    }

    const forceFull = new URLSearchParams(window.location.search).get("boot") === "full";
    const full = forceFull || !storage(store => store.getItem(SEEN_KEY));

    const term = Aether.console.create(document.getElementById("boot-output"), {
        flashTarget: document.getElementById("boot-screen")
    });

    async function run() {
        try {
            await term.play(full ? SCENES.full : SCENES.short, { speed: full ? 1 : 0.5 });
            storage(store => store.setItem(SEEN_KEY, "1"));   // только если дошли до конца
        } catch (error) {
            console.error(error);
        }

        window.location.href = "lock/";
    }

    run();
})();
