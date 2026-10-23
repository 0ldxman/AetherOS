/* =========================================================
   Aether Wiki — Scan Media
   Видео в формате архивного контактного листа.
   Обработка выполняется в браузере, без сохранения файлов.
   ========================================================= */

(function () {
    "use strict";

    const SELECTOR = ".doc--scan .widget--video";
    const VIDEO_SELECTOR = ".video-el";

    const FRAME_COUNT = 4;
    const FRAME_WIDTH = 480;
    const JPEG_QUALITY = 0.72;

    const LOAD_TIMEOUT = 15000;
    const SEEK_TIMEOUT = 8000;

    /*
     * Кэш действует только в пределах текущей страницы.
     *
     * key: URL видео
     * value: Promise с готовыми кадрами
     *
     * Promise позволяет не обрабатывать один файл несколько
     * раз, если он встретился в нескольких местах документа.
     */
    const frameCache = new Map();

    const initialized = new WeakSet();

    let observer = null;

    /* =====================================================
       Вспомогательные функции
       ===================================================== */

    function getVideoMetadata(widget, video, duration) {
        const filename = widget.dataset.fileName || "UNKNOWN";
        const assetId = widget.dataset.assetId || "UNKNOWN";
        const viewerUrl = widget.dataset.viewerUrl || "";

        const cleanName = filename.split(/[\\/]/).pop();

        const resolution = video.videoWidth && video.videoHeight
            ? video.videoWidth + " × " + video.videoHeight
            : "UNKNOWN";

        const status = document.createElement("div");
        status.className = "video-preview-status";

        const details = document.createElement("div");
        details.className = "video-preview-meta";

        const info = document.createElement("div");
        info.className = "video-preview-info";
        info.textContent =
            cleanName +
            " · DURATION: " + formatTime(duration) +
            " · RESOLUTION: " + resolution;

        details.appendChild(info);

        if (viewerUrl) {
            const link = document.createElement("a");
            link.className = "file-btn video-preview-id";
            link.href = viewerUrl;
            link.dataset.assetViewer = viewerUrl;
            link.dataset.assetTitle = cleanName;
            link.textContent = "ID: " + assetId;
            link.title = "Открыть видео в viewer";

            details.appendChild(link);
        } else {
            const id = document.createElement("span");
            id.className = "video-preview-id";
            id.textContent = "ID: " + assetId;

            details.appendChild(id);
        }

        status.appendChild(details);

        return status;
    }

    function formatTime(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) {
            return "00:00";
        }

        seconds = Math.floor(seconds);

        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;

        const mm = String(minutes).padStart(2, "0");
        const ss = String(secs).padStart(2, "0");

        if (hours > 0) {
            return (
                String(hours).padStart(2, "0") +
                ":" + mm +
                ":" + ss
            );
        }

        return mm + ":" + ss;
    }

    function waitForEvent(media, successEvent, timeoutMs) {
        return new Promise(function (resolve, reject) {
            let settled = false;

            const timeout = window.setTimeout(function () {
                finish(new Error("Превышено время ожидания: " + successEvent));
            }, timeoutMs);

            function cleanup() {
                window.clearTimeout(timeout);
                media.removeEventListener(successEvent, onSuccess);
                media.removeEventListener("error", onError);
                media.removeEventListener("abort", onAbort);
            }

            function finish(error) {
                if (settled) {
                    return;
                }

                settled = true;
                cleanup();

                if (error) {
                    reject(error);
                } else {
                    resolve();
                }
            }

            function onSuccess() {
                finish(null);
            }

            function onError() {
                finish(new Error("Ошибка чтения медиаданных"));
            }

            function onAbort() {
                finish(new Error("Загрузка медиаданных прервана"));
            }

            media.addEventListener(successEvent, onSuccess);
            media.addEventListener("error", onError);
            media.addEventListener("abort", onAbort);

            /*
            * Учитываем события, которые могли произойти раньше.
            * Для seeked такой проверки намеренно нет:
            * ожидание должно начинаться до изменения currentTime.
            */
            if (
                successEvent === "loadedmetadata" &&
                media.readyState >= HTMLMediaElement.HAVE_METADATA
            ) {
                finish(null);
            } else if (
                successEvent === "loadeddata" &&
                media.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA
            ) {
                finish(null);
            }
        });
    }


    function waitForSeek(video, targetTime, timeoutMs) {
        return new Promise(function (resolve, reject) {
            let settled = false;
            let timeoutId;
            let checkId;

            function cleanup() {
                window.clearTimeout(timeoutId);
                window.clearInterval(checkId);

                video.removeEventListener("seeked", checkSeek);
                video.removeEventListener("timeupdate", checkSeek);
                video.removeEventListener("error", onError);
                video.removeEventListener("abort", onAbort);
            }

            function finish(error) {
                if (settled) {
                    return;
                }

                settled = true;
                cleanup();

                if (error) {
                    reject(error);
                } else {
                    resolve();
                }
            }

            function checkSeek() {
                if (
                    !video.seeking &&
                    Number.isFinite(video.currentTime) &&
                    Math.abs(video.currentTime - targetTime) < 0.1 &&
                    video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA
                ) {
                    finish(null);
                }
            }

            function onError() {
                finish(new Error("Ошибка чтения видео при перемотке"));
            }

            function onAbort() {
                finish(new Error("Загрузка видео прервана при перемотке"));
            }

            video.addEventListener("seeked", checkSeek);
            video.addEventListener("timeupdate", checkSeek);
            video.addEventListener("error", onError);
            video.addEventListener("abort", onAbort);

            timeoutId = window.setTimeout(function () {
                finish(
                    new Error(
                        "Не удалось переместиться на " +
                        targetTime.toFixed(2) +
                        " с за отведённое время"
                    )
                );
            }, timeoutMs);

            /*
            * Некоторые браузеры не присылают seeked ожидаемым образом.
            * Проверяем фактическую позицию видео независимо от события.
            */
            checkId = window.setInterval(checkSeek, 100);

            checkSeek();
        });
    }


    function createStatus(preview, message) {
        let status = preview.querySelector(".video-preview-status");

        if (!status) {
            status = document.createElement("div");
            status.className = "video-preview-status";
            status.setAttribute("role", "status");
            preview.appendChild(status);
        }

        status.textContent = message;

        return status;
    }

    function createPreview(widget) {
        const preview = document.createElement("div");
        preview.className = "video-preview";
        preview.setAttribute("aria-label", "Архивный контактный лист видео");

        const grid = document.createElement("div");
        grid.className = "video-preview-grid";

        preview.appendChild(grid);

        /*
         * Вставляем превью перед исходным видео.
         * Сам video остаётся в DOM, но скрывается CSS.
         */
        widget.insertBefore(preview, widget.firstChild);

        return {
            root: preview,
            grid: grid
        };
    }

    function renderFrames(grid, frames) {
        grid.replaceChildren();

        frames.forEach(function (frame) {
            const tile = document.createElement("div");
            tile.className = "video-preview-frame";

            const image = document.createElement("img");
            image.src = frame.src;
            image.alt = "Кадр видео, " + formatTime(frame.time);
            image.loading = "lazy";
            image.decoding = "async";

            const timestamp = document.createElement("span");
            timestamp.className = "video-preview-time";
            timestamp.textContent = formatTime(frame.time);

            tile.appendChild(image);
            tile.appendChild(timestamp);
            grid.appendChild(tile);
        });
    }

    function getFrameTimes(duration) {
        /*
         * Берём кадры внутри длительности, не с самого начала
         * и не с последнего кадра, где часто бывает пустота.
         */
        const positions = [0.12, 0.38, 0.64, 0.88];

        return positions
            .slice(0, FRAME_COUNT)
            .map(function (position) {
                return Math.min(
                    Math.max(0, duration * position),
                    Math.max(0, duration - 0.05)
                );
            });
    }

    /* =====================================================
       Чтение кадров
       ===================================================== */

    async function extractFrames(sourceUrl) {
        const video = document.createElement("video");

        video.preload = "auto";
        video.muted = true;
        video.playsInline = true;
        video.controls = false;
        video.setAttribute("aria-hidden", "true");

        /*
         * Элемент должен быть загружен, но не отображаться.
         * display:none здесь не используется: отдельные браузеры
         * ведут себя с ним нестабильно при декодировании кадров.
         */
        video.style.position = "fixed";
        video.style.left = "-10000px";
        video.style.top = "0";
        video.style.width = "1px";
        video.style.height = "1px";
        video.style.opacity = "0";
        video.style.pointerEvents = "none";

        document.body.appendChild(video);

        try {
            const metadataPromise = waitForEvent(
                video,
                "loadedmetadata",
                LOAD_TIMEOUT
            );

            video.src = sourceUrl;
            video.load();

            await metadataPromise;

            const duration = video.duration;

            if (!Number.isFinite(duration) || duration <= 0) {
                throw new Error("Не удалось определить длительность видео");
            }

            if (!video.videoWidth || !video.videoHeight) {
                throw new Error("Видео не содержит доступных кадров");
            }

            const aspectRatio = video.videoWidth / video.videoHeight;

            const times = getFrameTimes(duration);
            const frames = [];

            const canvas = document.createElement("canvas");
            const context = canvas.getContext("2d", {
                alpha: false
            });

            if (!context) {
                throw new Error("Canvas недоступен");
            }

            const scale = Math.min(
                1,
                FRAME_WIDTH / video.videoWidth
            );

            canvas.width = Math.max(
                1,
                Math.round(video.videoWidth * scale)
            );

            canvas.height = Math.max(
                1,
                Math.round(video.videoHeight * scale)
            );

            for (const time of times) {
                /*
                 * Если видео уже находится на нужном времени,
                 * принудительный seek не нужен.
                 */
                if (Math.abs(video.currentTime - time) > 0.01) {
                    const seekPromise = waitForSeek(
                        video,
                        time,
                        SEEK_TIMEOUT
                    );

                    video.currentTime = time;

                    await seekPromise;
                }

                if (
                    video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA
                ) {
                    await waitForEvent(
                        video,
                        "loadeddata",
                        LOAD_TIMEOUT
                    );
                }

                context.drawImage(
                    video,
                    0,
                    0,
                    canvas.width,
                    canvas.height
                );

                frames.push({
                    time: time,
                    src: canvas.toDataURL(
                        "image/jpeg",
                        JPEG_QUALITY
                    )
                });
            }

            return {
                duration: duration,
                width: video.videoWidth,
                height: video.videoHeight,
                aspectRatio: aspectRatio,
                frames: frames
            };
        } finally {
            video.pause();
            video.removeAttribute("src");
            video.load();
            video.remove();
        }
    }

    /* =====================================================
       Обработка одного виджета
       ===================================================== */

    
    async function processWidget(widget) {
        if (initialized.has(widget)) {
            return;
        }

        initialized.add(widget);

        const video = widget.querySelector(VIDEO_SELECTOR);

        if (!video) {
            return;
        }

        const sourceUrl = video.currentSrc || video.src;

        const previewParts = createPreview(widget);
        const preview = previewParts.root;
        const grid = previewParts.grid;

        if (!sourceUrl) {
            preview.classList.add("video-preview--failed");
            createStatus(
                preview,
                "ПРЕДПРОСМОТР НЕДОСТУПЕН — ИСТОЧНИК НЕ УКАЗАН"
            );
            return;
        }

        createStatus(preview, "ИЗВЛЕЧЕНИЕ КАДРОВ…");

        let cachedPromise = frameCache.get(sourceUrl);

        if (!cachedPromise) {
            cachedPromise = extractFrames(sourceUrl);
            frameCache.set(sourceUrl, cachedPromise);
        }

        try {
            const result = await cachedPromise;

            renderFrames(grid, result.frames);

            grid.style.setProperty(
                "--frame-ratio",
                result.width + " / " + result.height
            );

            preview.classList.remove("video-preview--failed");

            const oldStatus = preview.querySelector(
                ".video-preview-status"
            );

            if (oldStatus) {
                oldStatus.remove();
            }

            preview.appendChild(
                getVideoMetadata(widget, video, result.duration)
            );

        } catch (error) {
            /*
            * Удаляем неудачный Promise из кэша,
            * чтобы обработку можно было повторить.
            */
            if (frameCache.get(sourceUrl) === cachedPromise) {
                frameCache.delete(sourceUrl);
            }

            preview.classList.add("video-preview--failed");

            createStatus(
                preview,
                "ПРЕДПРОСМОТР НЕДОСТУПЕН — ФОРМАТ НЕ ПОДДЕРЖИВАЕТСЯ ИЛИ ПОТОК НЕ ЧИТАЕТСЯ"
            );

            console.warn(
                "[Aether Wiki] Не удалось создать видеопревью:",
                sourceUrl,
                error
            );
        }
    }


    /* =====================================================
       Инициализация и ленивая обработка
       ===================================================== */

    function scan(root) {
        if (!root || !root.querySelectorAll) {
            return;
        }

        if (
            root.matches &&
            root.matches(SELECTOR) &&
            !initialized.has(root)
        ) {
            observeWidget(root);
        }

        root.querySelectorAll(SELECTOR).forEach(function (widget) {
            observeWidget(widget);
        });
    }

    function observeWidget(widget) {
        if (initialized.has(widget)) {
            return;
        }

        if (observer) {
            observer.observe(widget);
        } else {
            processWidget(widget);
        }
    }

    function init() {
        if ("IntersectionObserver" in window) {
            observer = new IntersectionObserver(
                function (entries) {
                    entries.forEach(function (entry) {
                        if (!entry.isIntersecting) {
                            return;
                        }

                        observer.unobserve(entry.target);
                        processWidget(entry.target);
                    });
                },
                {
                    root: null,
                    rootMargin: "400px 0px",
                    threshold: 0
                }
            );
        }

        scan(document);

        /*
         * Поддержка документов, которые подгружаются в DOM
         * после первоначальной загрузки страницы.
         */
        const mutationObserver = new MutationObserver(function (records) {
            records.forEach(function (record) {
                record.addedNodes.forEach(function (node) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        scan(node);
                    }
                });
            });
        });

        mutationObserver.observe(document.documentElement, {
            childList: true,
            subtree: true
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, {
            once: true
        });
    } else {
        init();
    }
})();