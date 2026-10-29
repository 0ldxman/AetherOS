/* ==================================================
   AETHER WIKI / DOCUMENT LOCK
   Пока страница записи открыта в админке, раз в несколько
   секунд сообщает серверу об этом (wiki/admin_locks.py).
   Если запись правит кто-то ещё, показывает предупреждение.
   При закрытии страницы блокировка снимается.
   ================================================== */

(function () {
    "use strict";

    const banner = document.getElementById("wp-lock");

    if (!banner) {
        return;
    }

    const lockUrl = banner.dataset.lockUrl;
    const unlockUrl = banner.dataset.unlockUrl;
    const interval = Number(banner.dataset.interval) || 25000;

    const tokenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    const token = tokenInput ? tokenInput.value : "";

    function show(holder) {
        if (!holder) {
            banner.hidden = true;
            return;
        }

        banner.textContent =
            "Сейчас эту запись правит " + holder.name +
            " (с " + holder.since + "). " +
            "Если сохранить, чужие правки могут быть заменены.";
        banner.hidden = false;
    }

    async function beat() {
        if (document.hidden) {
            return;
        }

        try {
            const response = await fetch(lockUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: { "X-CSRFToken": token },
            });
            const data = await response.json();

            if (data.ok) {
                show(data.holder);
            }
        } catch (error) {
            // нет связи: предупреждение не обязательно, следующая попытка через интервал
        }
    }

    function release() {
        const body = new FormData();

        body.append("csrfmiddlewaretoken", token);
        navigator.sendBeacon(unlockUrl, body);
    }

    beat();
    setInterval(beat, interval);

    document.addEventListener("visibilitychange", function () {
        if (!document.hidden) {
            beat();
        }
    });

    window.addEventListener("pagehide", release);
})();
