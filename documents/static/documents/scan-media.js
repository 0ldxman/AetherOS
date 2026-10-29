/* =========================================================
   Aether Wiki — Scan Media
   Архивный контактный лист видео.
   Метаданные и кадры загружаются независимо по этапам.
   ========================================================= */

(function () {
    "use strict";

    const SELECTOR = ".doc--scan .widget--video";
    const VIDEO_SELECTOR = ".video-el";

    const FRAME_COUNT = 4;
    const FRAME_WIDTH = 480;
    const JPEG_QUALITY = 0.72;

    const LOAD_TIMEOUT = 30000;
    const SEEK_TIMEOUT = 10000;

    const frameCache = new Map();
    const initialized = new WeakSet();

    let observer = null;

    /* =====================================================
       Форматирование
       ===================================================== */

    function formatTime(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) {
            return "--:--";
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

    function getFileInfo(widget) {
        const filename =
            widget.dataset.fileName || "UNKNOWN";

        return {
            filename: filename.split(/[\\/]/).pop(),
            assetId: widget.dataset.assetId || "UNKNOWN",
            viewerUrl: widget.dataset.viewerUrl || ""
        };
    }

    /* =====================================================
       Метаданные

       Блок создаётся сразу. До loadedmetadata отображаются
       имя файла и ID, остальные поля заполняются позднее.
       ===================================================== */

    function createMetadataElement(widget) {
        const status = document.createElement("div");
        status.className = "video-preview-status";
        status.setAttribute("role", "status");

        const details = document.createElement("div");
        details.className = "video-preview-meta";

        const info = document.createElement("div");
        info.className = "video-preview-info";

        const id = document.createElement("span");
        const file = getFileInfo(widget);

        info.textContent =
            file.filename +
            " · DURATION: --:--" +
            " · RESOLUTION: UNKNOWN";

        if (file.viewerUrl) {
            const link = document.createElement("a");

            link.className = "file-btn video-preview-id";
            link.href = file.viewerUrl;
            link.dataset.assetViewer = file.viewerUrl;
            link.dataset.assetTitle = file.filename;
            link.textContent = "ID: " + file.assetId;
            link.title = "Открыть видео в viewer";

            id.replaceWith(link);
            details.append(info, link);
        } else {
            id.className = "video-preview-id";
            id.textContent = "ID: " + file.assetId;

            details.append(info, id);
        }

        status.appendChild(details);

        return status;
    }

    function updateMetadataElement(element, widget, metadata) {
        const file = getFileInfo(widget);

        const resolution =
            metadata &&
            metadata.width > 0 &&
            metadata.height > 0
                ? metadata.width + " × " + metadata.height
                : "UNKNOWN";

        const duration =
            metadata && Number.isFinite(metadata.duration)
                ? formatTime(metadata.duration)
                : "--:--";

        const info = element.querySelector(".video-preview-info");

        if (info) {
            info.textContent =
                file.filename +
                " · DURATION: " + duration +
                " · RESOLUTION: " + resolution;
        }
    }

    /* =====================================================
       События медиа
       ===================================================== */

    function waitForEvent(media, successEvent, timeoutMs) {
        return new Promise(function (resolve, reject) {
            let settled = false;

            const timeout = window.setTimeout(function () {
                finish(
                    new Error(
                        "Превышено время ожидания: " + successEvent
                    )
                );
            }, timeoutMs);

            function cleanup() {
                window.clearTimeout(timeout);

                media.removeEventListener(successEvent, onSuccess);
                media.removeEventListener("error", onError);
                media.removeEventListener("abort", onAbort);
                media.removeEventListener("stalled", onStalled);
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
                const mediaError = media.error;

                finish(
                    new Error(
                        "Ошибка декодирования видео" +
                        (
                            mediaError
                                ? " (код " + mediaError.code + ")"
                                : ""
                        )
                    )
                );
            }

            function onAbort() {
                finish(new Error("Загрузка видео прервана"));
            }

            function onStalled() {
                /* Не завершаем ожидание: браузер может продолжить загрузку. */
            }

            media.addEventListener(successEvent, onSuccess);
            media.addEventListener("error", onError);
            media.addEventListener("abort", onAbort);
            media.addEventListener("stalled", onStalled);

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


    function waitForSeek(video, time) {
        return new Promise((resolve, reject) => {
            const cleanup = () => {
                video.removeEventListener("seeked", onSeeked);
                video.removeEventListener("error", onError);
            };

            const onSeeked = () => {
                cleanup();
                resolve();
            };

            const onError = () => {
                cleanup();
                reject(
                    video.error ||
                    new Error("Ошибка декодирования видео")
                );
            };

            // Сначала подписываемся, затем начинаем перемотку.
            video.addEventListener("seeked", onSeeked);
            video.addEventListener("error", onError);

            if (Math.abs(video.currentTime - time) < 0.01) {
                cleanup();
                resolve();
                return;
            }

            video.currentTime = time;
        });
    }


    /* =====================================================
       Превью и геометрия
       ===================================================== */

    function createPreview(widget) {
        const preview = document.createElement("div");

        preview.className = "video-preview";
        preview.setAttribute(
            "aria-label",
            "Архивный контактный лист видео"
        );

        const grid = document.createElement("div");
        grid.className = "video-preview-grid";

        /*
         * Если исходный плеер уже знает размеры, используем
         * их для заглушек ещё до запуска декодера.
         */
        const sourceVideo = widget.querySelector(VIDEO_SELECTOR);

        let initialRatio = null;

        if (
            sourceVideo &&
            sourceVideo.videoWidth > 0 &&
            sourceVideo.videoHeight > 0
        ) {
            initialRatio =
                sourceVideo.videoWidth / sourceVideo.videoHeight;
        }

        for (let index = 0; index < FRAME_COUNT; index += 1) {
            const tile = document.createElement("div");

            tile.className =
                "video-preview-frame video-preview-frame--pending";

            tile.dataset.frameIndex = String(index);
            tile.setAttribute("aria-hidden", "true");

            if (initialRatio) {
                tile.style.aspectRatio =
                    sourceVideo.videoWidth + " / " +
                    sourceVideo.videoHeight;
            }

            grid.appendChild(tile);
        }

        preview.appendChild(grid);

        const metadataElement = createMetadataElement(widget);
        preview.appendChild(metadataElement);

        widget.insertBefore(preview, widget.firstChild);

        return {
            root: preview,
            grid: grid,
            metadata: metadataElement
        };
    }

    function setFrameAspectRatio(grid, metadata) {
        if (
            !metadata ||
            !Number.isFinite(metadata.width) ||
            !Number.isFinite(metadata.height) ||
            metadata.width <= 0 ||
            metadata.height <= 0
        ) {
            return;
        }

        const ratio =
            metadata.width + " / " + metadata.height;

        /*
         * Задаём ratio непосредственно каждой плитке.
         * Это исключает зависимость от наследования CSS-переменной.
         */
        grid.querySelectorAll(".video-preview-frame").forEach(
            function (tile) {
                tile.style.aspectRatio = ratio;
            }
        );
    }

    function getFrameTimes(duration) {
        return [0.12, 0.38, 0.64, 0.88]
            .slice(0, FRAME_COUNT)
            .map(function (position) {
                return Math.min(
                    Math.max(0, duration * position),
                    Math.max(0, duration - 0.05)
                );
            });
    }

    /* =====================================================
       Отображение кадров
       ===================================================== */

    function renderFrame(grid, frame) {
        const tile = grid.querySelector(
            '[data-frame-index="' + frame.index + '"]'
        );

        if (!tile || tile.dataset.frameReady === "true") {
            return;
        }

        tile.dataset.frameReady = "true";
        tile.classList.remove("video-preview-frame--pending");
        tile.classList.add("video-preview-frame--loading");

        const image = document.createElement("img");

        image.className = "video-preview-image";
        image.alt = "Кадр видео, " + formatTime(frame.time);
        image.decoding = "async";
        image.draggable = false;

        const timestamp = document.createElement("span");

        timestamp.className = "video-preview-time";
        timestamp.textContent = formatTime(frame.time);

        image.addEventListener("load", function () {
            window.requestAnimationFrame(function () {
                tile.classList.remove("video-preview-frame--loading");
                tile.classList.add("video-preview-frame--revealed");
            });
        }, { once: true });

        image.addEventListener("error", function () {
            tile.classList.remove("video-preview-frame--loading");
            tile.classList.add("video-preview-frame--error");
        }, { once: true });

        tile.append(image, timestamp);
        image.src = frame.src;
    }

    /* =====================================================
       Извлечение кадров

       Важно: исходный URL назначается непосредственно video.src.
       Весь файл не скачивается заранее через fetch() и blob().
       Браузер сам загружает необходимые диапазоны данных.
       ===================================================== */

    async function extractFrames(sourceUrl, onMetadata, onFrame) {
        const video = document.createElement("video");

        video.preload = "auto";
        video.muted = true;
        video.playsInline = true;
        video.controls = false;
        video.setAttribute("aria-hidden", "true");

        video.style.position = "fixed";
        video.style.left = "-10000px";
        video.style.top = "0";
        video.style.width = "1px";
        video.style.height = "1px";
        video.style.opacity = "0";
        video.style.pointerEvents = "none";

        document.body.appendChild(video);

        try {
            /*
             * Сначала регистрируем обработчик, затем назначаем URL,
             * чтобы не пропустить loadedmetadata.
             */
            const metadataPromise = waitForEvent(
                video,
                "loadedmetadata",
                LOAD_TIMEOUT
            );

            video.src = sourceUrl;
            video.load();

            await metadataPromise;

            const duration = video.duration;
            const width = video.videoWidth;
            const height = video.videoHeight;

            if (!Number.isFinite(duration) || duration <= 0) {
                throw new Error(
                    "Браузер не смог определить длительность видео"
                );
            }

            if (width <= 0 || height <= 0) {
                throw new Error(
                    "Браузер не смог определить разрешение видео"
                );
            }

            const metadata = {
                duration: duration,
                width: width,
                height: height,
                aspectRatio: width / height
            };

            /*
             * Метаданные публикуются до декодирования кадров.
             */
            if (typeof onMetadata === "function") {
                onMetadata(metadata);
            }

            const canvas = document.createElement("canvas");
            const context = canvas.getContext("2d", {
                alpha: false
            });

            if (!context) {
                throw new Error("Canvas 2D недоступен");
            }

            const scale = Math.min(1, FRAME_WIDTH / width);

            canvas.width = Math.max(1, Math.round(width * scale));
            canvas.height = Math.max(1, Math.round(height * scale));

            const times = getFrameTimes(duration);
            const frames = [];


            for (const time of times) {
                await waitForSeek(video, time);

                // После seeked ждём, пока браузер получит данные для кадра.
                if (
                    video.readyState <
                    HTMLMediaElement.HAVE_CURRENT_DATA
                ) {
                    await waitForEvent(
                        video,
                        "loadeddata",
                        LOAD_TIMEOUT
                    );
                }

                // Даём браузеру возможность завершить отрисовку декодированного кадра.
                await new Promise(resolve => {
                    requestAnimationFrame(() => {
                        requestAnimationFrame(resolve);
                    });
                });

                context.drawImage(
                    video,
                    0,
                    0,
                    canvas.width,
                    canvas.height
                );

                const frame = {
                    index: frames.length,
                    time: time,
                    src: canvas.toDataURL(
                        "image/jpeg",
                        JPEG_QUALITY
                    )
                };

                frames.push(frame);

                if (typeof onFrame === "function") {
                    onFrame(frame);
                }
            }


            return {
                duration: duration,
                width: width,
                height: height,
                aspectRatio: width / height,
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
       Кэш общей задачи
       ===================================================== */

    function getFrameTask(sourceUrl) {
        const cached = frameCache.get(sourceUrl);

        if (cached) {
            return cached;
        }

        const task = {
            frames: [],
            subscribers: new Set(),
            metadata: null,
            metadataSubscribers: new Set(),
            promise: null
        };

        /*
         * Запускаем задачу один раз на URL.
         * Подписчики получают метаданные и кадры независимо.
         */
        task.promise = extractFrames(
            sourceUrl,

            function (metadata) {
                task.metadata = metadata;

                task.metadataSubscribers.forEach(function (subscriber) {
                    try {
                        subscriber(metadata);
                    } catch (error) {
                        console.error(
                            "[Aether Wiki] Ошибка обновления метаданных:",
                            error
                        );
                    }
                });
            },

            function (frame) {
                task.frames[frame.index] = frame;

                task.subscribers.forEach(function (subscriber) {
                    try {
                        subscriber(frame);
                    } catch (error) {
                        console.error(
                            "[Aether Wiki] Ошибка отображения кадра:",
                            error
                        );
                    }
                });
            }
        );

        frameCache.set(sourceUrl, task);

        return task;
    }

    /* =====================================================
       Обработка виджета
       ===================================================== */

    async function processWidget(widget) {
        if (initialized.has(widget)) {
            return;
        }

        initialized.add(widget);

        const sourceVideo = widget.querySelector(VIDEO_SELECTOR);

        if (!sourceVideo) {
            return;
        }

        const sourceUrl =
            sourceVideo.currentSrc ||
            sourceVideo.src ||
            sourceVideo.getAttribute("src");

        const parts = createPreview(widget);
        const preview = parts.root;
        const grid = parts.grid;
        const metadataElement = parts.metadata;

        /*
         * Имя файла и ID уже видны. Длительность и разрешение
         * пока имеют значения-заполнители.
         */
        if (!sourceUrl) {
            preview.classList.add("video-preview--failed");
            showError(preview, "ИСТОЧНИК ВИДЕО НЕ УКАЗАН");
            return;
        }

        const task = getFrameTask(sourceUrl);

        function onMetadata(metadata) {
            updateMetadataElement(
                metadataElement,
                widget,
                metadata
            );

            setFrameAspectRatio(grid, metadata);
        }

        function onFrame(frame) {
            renderFrame(grid, frame);
        }

        task.metadataSubscribers.add(onMetadata);
        task.subscribers.add(onFrame);

        /*
         * Если задача уже выполняется, немедленно отображаем
         * имеющиеся метаданные и ранее извлечённые кадры.
         */
        if (task.metadata) {
            onMetadata(task.metadata);
        }

        task.frames.forEach(function (frame) {
            if (frame) {
                onFrame(frame);
            }
        });

        try {
            const result = await task.promise;

            onMetadata(result);

            preview.classList.remove("video-preview--failed");
        } catch (error) {
            if (frameCache.get(sourceUrl) === task) {
                frameCache.delete(sourceUrl);
            }

            /*
             * Не скрываем сетку: уже извлечённые кадры остаются.
             * Ошибка отображается отдельно от метаданных.
             */
            showError(
                preview,
                "НЕ УДАЛОСЬ ИЗВЛЕЧЬ ВСЕ КАДРЫ"
            );

            console.warn(
                "[Aether Wiki] Не удалось создать видеопревью:",
                sourceUrl,
                error
            );
        } finally {
            task.subscribers.delete(onFrame);
            task.metadataSubscribers.delete(onMetadata);
        }
    }

    function showError(preview, message) {
        let errorElement = preview.querySelector(
            ".video-preview-error"
        );

        if (!errorElement) {
            errorElement = document.createElement("div");
            errorElement.className = "video-preview-error";
            errorElement.setAttribute("role", "status");

            preview.appendChild(errorElement);
        }

        errorElement.textContent = message;
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