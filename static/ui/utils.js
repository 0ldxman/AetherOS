/* ==================================================
   AETHER OS / UI UTILS
   Общие помощники для вьюверов ассетов и вики-виджетов.
   Подключается перед скриптами, которые ими пользуются.
   ================================================== */

(function () {
    "use strict";

    const Aether = (window.Aether = window.Aether || {});

    /** Секунды -> "мм:сс". Мусор и отрицательные значения дают "00:00". */
    Aether.formatTime = function (seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) {
            return "00:00";
        }

        const total = Math.floor(seconds);
        const minutes = Math.floor(total / 60);

        return (
            String(minutes).padStart(2, "0") +
            ":" +
            String(total % 60).padStart(2, "0")
        );
    };

    /** Байты -> "12 B" / "1.50 KB" / "3.20 MB" / "1.00 GB". */
    Aether.formatSize = function (bytes) {
        const units = ["B", "KB", "MB", "GB"];
        let value = bytes;
        let unit = 0;

        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024;
            unit += 1;
        }

        return unit === 0
            ? value + " B"
            : value.toFixed(2) + " " + units[unit];
    };

    /**
     * Входит в полноэкранный режим или выходит из него.
     * element: что раскрывать. fallbackVideo: <video> для iOS, где
     * requestFullscreen недоступен. Возвращает false, если браузер отказал
     * (например, в iframe без разрешения).
     */
    Aether.toggleFullscreen = async function (element, fallbackVideo) {
        try {
            if (document.fullscreenElement) {
                await document.exitFullscreen();
            } else if (element.requestFullscreen) {
                await element.requestFullscreen();
            } else if (fallbackVideo && fallbackVideo.webkitEnterFullscreen) {
                fallbackVideo.webkitEnterFullscreen();
            }
            return true;
        } catch (error) {
            return false;
        }
    };
})();
