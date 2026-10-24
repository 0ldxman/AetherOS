/* ==================================================
   AETHER OS / VIDEO WIDGET
   Встроенный плеер для .doc--rec и .doc--infobox.
   Берёт обычный <video controls> из _render_video и
   собирает вокруг него плеер в стиле видео-просмотрщика.
   Без JS остаётся родной плеер браузера.
   ================================================== */

(function () {
    "use strict";

    const SELECTOR = ".doc--rec .widget--video, .doc--infobox .widget--video";
    const AUTO_HIDE_DELAY = 2200;

    const ICON_PLAY = '<path d="M8 5.5 19 12 8 18.5Z" />';
    const ICON_PAUSE = '<path d="M7 5h4v14H7zM15 5h4v14h-4z" />';

    const SPEEDS = ["0.5", "0.75", "1", "1.25", "1.5", "2"];

    const formatTime = Aether.formatTime;

    function template(hasViewer) {
        const speedOptions = SPEEDS.map(function (v) {
            return `<option value="${v}"${v === "1" ? " selected" : ""}>${v}×</option>`;
        }).join("");

        const openButton = hasViewer
            ? `<a class="vw-btn vw-open" title="Open in viewer" aria-label="Open in viewer">
                   <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-8 8M18 14v6H4V6h6" /></svg>
               </a>`
            : "";

        return `
            <button class="vw-center" type="button" aria-label="Play video">
                <svg viewBox="0 0 24 24" aria-hidden="true">${ICON_PLAY}</svg>
            </button>

            <div class="vw-error" hidden>
                <span>VIDEO / ERROR</span>
                <p></p>
            </div>

            <header class="vw-meta">
                <div class="vw-title">
                    <span class="vw-format"></span>
                    <b class="vw-name"></b>
                </div>
                <div class="vw-info"><span class="vw-label">ID:</span><span class="vw-value vw-id"></span></div>
                <div class="vw-info"><span class="vw-label">RESOLUTION:</span><span class="vw-value vw-res">—</span></div>
                <div class="vw-info"><span class="vw-label">DURATION:</span><span class="vw-value vw-dur">—</span></div>
            </header>

            <div class="vw-status">READY</div>

            <div class="vw-controls">
                <div class="vw-progress-row">
                    <span class="vw-time vw-cur">00:00</span>
                    <input class="vw-progress" type="range" min="0" max="1000" value="0" step="1" aria-label="Seek video">
                    <span class="vw-time vw-total">00:00</span>
                </div>

                <div class="vw-row">
                    <div class="vw-group">
                        <button class="vw-btn vw-play" type="button" aria-label="Play" title="Play (Space)">
                            <svg viewBox="0 0 24 24" aria-hidden="true">${ICON_PLAY}</svg>
                        </button>
                        <button class="vw-btn vw-mute" type="button" aria-label="Mute" title="Mute (M)">
                            <svg viewBox="0 0 24 24" aria-hidden="true">
                                <path d="M4 9v6h4l5 4V5L8 9H4Z" />
                                <path class="vw-wave" d="M16 9a4 4 0 0 1 0 6" />
                                <path class="vw-cross" d="m17 9 5 6m0-6-5 6" hidden />
                            </svg>
                        </button>
                        <input class="vw-volume" type="range" min="0" max="1" value="1" step="0.01" aria-label="Volume">
                    </div>

                    <div class="vw-group vw-group-right">
                        <label class="vw-speed">
                            <span>SPEED</span>
                            <select aria-label="Playback speed">${speedOptions}</select>
                        </label>
                        ${openButton}
                        <button class="vw-btn vw-fs" type="button" aria-label="Enter fullscreen" title="Fullscreen (F)">
                            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" /></svg>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    function build(figure) {
        if (figure.dataset.vwReady) {
            return;
        }

        const video = figure.querySelector("video.video-el");

        if (!video) {
            return;
        }

        figure.dataset.vwReady = "1";

        /* ---------- Каркас ---------- */

        const fileName = figure.dataset.fileName || "";
        const dot = fileName.lastIndexOf(".");
        const title = dot > 0 ? fileName.slice(0, dot) : fileName;
        const extension = dot > 0 ? fileName.slice(dot + 1).toUpperCase() : "UNKNOWN";
        const viewerUrl = figure.dataset.viewerUrl || "";

        const stage = document.createElement("div");
        stage.className = "vw-stage";
        stage.tabIndex = 0;

        video.removeAttribute("controls");
        video.setAttribute("playsinline", "");
        video.disablePictureInPicture = true;
        video.classList.add("vw-source");

        figure.insertBefore(stage, video);
        stage.appendChild(video);
        stage.insertAdjacentHTML("beforeend", template(Boolean(viewerUrl)));

        const q = function (selector) {
            return stage.querySelector(selector);
        };

        const center = q(".vw-center");
        const errorBox = q(".vw-error");
        const errorText = q(".vw-error p");
        const meta = q(".vw-meta");
        const controls = q(".vw-controls");
        const status = q(".vw-status");
        const resolution = q(".vw-res");
        const duration = q(".vw-dur");
        const current = q(".vw-cur");
        const total = q(".vw-total");
        const progress = q(".vw-progress");
        const playButton = q(".vw-play");
        const playIcon = q(".vw-play svg");
        const centerIcon = q(".vw-center svg");
        const muteButton = q(".vw-mute");
        const wave = q(".vw-wave");
        const cross = q(".vw-cross");
        const volume = q(".vw-volume");
        const speed = q(".vw-speed select");
        const fsButton = q(".vw-fs");
        const openLink = q(".vw-open");

        q(".vw-format").textContent = `[VIDEO.${extension}]`;
        q(".vw-name").textContent = title;
        q(".vw-id").textContent = figure.dataset.assetId || "—";

        if (openLink && viewerUrl) {
            openLink.setAttribute("href", viewerUrl);
            openLink.setAttribute("data-asset-viewer", viewerUrl);
            openLink.setAttribute("data-asset-title", fileName);
            openLink.addEventListener("click", function () {
                video.pause();
            });
        }

        let hideTimer = null;
        let seeking = false;
        let failed = false;

        /* ---------- Метаданные ---------- */

        function updateMetadata() {
            if (video.videoWidth && video.videoHeight) {
                resolution.textContent = `${video.videoWidth} × ${video.videoHeight}`;
                stage.style.setProperty(
                    "--vw-ratio",
                    `${video.videoWidth} / ${video.videoHeight}`
                );
            }

            duration.textContent = formatTime(video.duration);
            total.textContent = formatTime(video.duration);
        }

        /* ---------- Показ и скрытие ---------- */

        function showControls() {
            clearTimeout(hideTimer);
            stage.classList.remove("vw-hidden");
        }

        function scheduleHide() {
            clearTimeout(hideTimer);

            if (video.paused || video.ended || failed || seeking) {
                showControls();
                return;
            }

            hideTimer = setTimeout(function () {
                if (!controls.matches(":hover")) {
                    stage.classList.add("vw-hidden");
                }
            }, AUTO_HIDE_DELAY);
        }

        /* ---------- Статус, ошибки ---------- */

        function setStatus(value) {
            status.textContent = value;
        }

        function showError(message) {
            failed = true;
            showControls();

            errorText.textContent = message || "Unable to load video source.";
            errorBox.hidden = false;
            center.hidden = true;
            setStatus("ERROR");
        }

        /* ---------- Воспроизведение ---------- */

        function updatePlayState() {
            const playing = !video.paused && !video.ended;
            const icon = playing ? ICON_PAUSE : ICON_PLAY;

            stage.classList.toggle("vw-playing", playing);

            playIcon.innerHTML = icon;
            playButton.setAttribute("aria-label", playing ? "Pause" : "Play");
            playButton.title = playing ? "Pause (Space)" : "Play (Space)";
            centerIcon.innerHTML = ICON_PLAY;
            center.hidden = playing || failed;

            if (failed) {
                setStatus("ERROR");
            } else if (video.ended) {
                setStatus("END OF FILE");
            } else if (playing) {
                setStatus("PLAYING");
            } else if (video.currentTime > 0) {
                setStatus("PAUSED");
            } else {
                setStatus("READY");
            }
        }

        async function togglePlayback() {
            if (failed) {
                return;
            }

            if (video.paused || video.ended) {
                if (video.ended) {
                    video.currentTime = 0;
                }

                try {
                    await video.play();
                } catch (err) {
                    showError("Playback could not be started. The format may not be supported by this browser.");
                }
            } else {
                video.pause();
            }

            showControls();
        }

        playButton.addEventListener("click", togglePlayback);
        center.addEventListener("click", togglePlayback);
        video.addEventListener("click", togglePlayback);

        video.addEventListener("play", function () {
            updatePlayState();
            scheduleHide();
        });

        video.addEventListener("playing", function () {
            updatePlayState();
            scheduleHide();
        });

        video.addEventListener("pause", function () {
            updatePlayState();
            showControls();
        });

        video.addEventListener("ended", function () {
            updatePlayState();
            showControls();
        });

        video.addEventListener("waiting", function () {
            if (!video.paused) {
                setStatus("BUFFERING");
            }
        });

        /* ---------- Таймлайн ---------- */

        function paintProgress(fraction) {
            progress.style.setProperty("--vw-progress", `${fraction * 100}%`);
        }

        function updateProgress() {
            current.textContent = formatTime(video.currentTime);

            if (!seeking && Number.isFinite(video.duration) && video.duration > 0) {
                const value = Math.round((video.currentTime / video.duration) * 1000);

                progress.value = String(value);
                paintProgress(value / 1000);
            }
        }

        progress.addEventListener("pointerdown", function () {
            seeking = true;
            showControls();
        });

        progress.addEventListener("input", function () {
            const fraction = Number(progress.value) / 1000;

            paintProgress(fraction);

            if (Number.isFinite(video.duration) && video.duration > 0) {
                video.currentTime = fraction * video.duration;
                current.textContent = formatTime(video.currentTime);
            }
        });

        function endSeek() {
            if (seeking) {
                seeking = false;
                scheduleHide();
            }
        }

        progress.addEventListener("pointerup", endSeek);
        progress.addEventListener("change", endSeek);

        video.addEventListener("timeupdate", updateProgress);
        video.addEventListener("durationchange", updateMetadata);

        /* ---------- Громкость ---------- */

        function updateVolumeUI() {
            const silent = video.muted || video.volume === 0;

            volume.value = String(video.muted ? 0 : video.volume);
            muteButton.setAttribute("aria-label", silent ? "Unmute" : "Mute");
            wave.hidden = silent;
            cross.hidden = !silent;
        }

        muteButton.addEventListener("click", function () {
            video.muted = !video.muted;
            showControls();
        });

        volume.addEventListener("input", function () {
            video.volume = Number(volume.value);
            video.muted = video.volume === 0;
            showControls();
        });

        video.addEventListener("volumechange", updateVolumeUI);

        /* ---------- Скорость ---------- */

        speed.addEventListener("change", function () {
            video.playbackRate = Number(speed.value);
            showControls();
        });

        /* ---------- Полный экран ---------- */

        function isFullscreen() {
            return document.fullscreenElement === stage;
        }

        async function toggleFullscreen() {
            await Aether.toggleFullscreen(stage, video);

            showControls();
        }

        function updateFullscreenUI() {
            const active = isFullscreen();

            stage.classList.toggle("vw-fullscreen", active);
            fsButton.setAttribute("aria-label", active ? "Exit fullscreen" : "Enter fullscreen");
            fsButton.title = active ? "Exit fullscreen (F)" : "Fullscreen (F)";
        }

        fsButton.addEventListener("click", toggleFullscreen);
        document.addEventListener("fullscreenchange", updateFullscreenUI);

        /* ---------- Мышь и клавиатура ---------- */

        stage.addEventListener("pointermove", function () {
            showControls();
            scheduleHide();
        });

        stage.addEventListener("pointerleave", scheduleHide);
        controls.addEventListener("pointerleave", scheduleHide);

        stage.addEventListener("keydown", function (event) {
            if (event.defaultPrevented || event.ctrlKey || event.altKey || event.metaKey) {
                return;
            }

            const tag = event.target instanceof HTMLElement ? event.target.tagName : "";

            if (tag === "INPUT" || tag === "SELECT") {
                return;
            }

            if (tag === "BUTTON" && event.key === " ") {
                return;
            }

            switch (event.key.toLowerCase()) {
                case " ":
                    event.preventDefault();
                    togglePlayback();
                    break;

                case "arrowleft":
                    event.preventDefault();
                    video.currentTime = Math.max(0, video.currentTime - 5);
                    break;

                case "arrowright":
                    event.preventDefault();
                    video.currentTime = Number.isFinite(video.duration)
                        ? Math.min(video.duration, video.currentTime + 5)
                        : video.currentTime + 5;
                    break;

                case "m":
                    video.muted = !video.muted;
                    break;

                case "f":
                    toggleFullscreen();
                    break;

                default:
                    return;
            }

            showControls();
            scheduleHide();
        });

        /* ---------- Загрузка ---------- */

        video.addEventListener("loadedmetadata", function () {
            updateMetadata();
            updateProgress();
            updatePlayState();
        });

        video.addEventListener("error", function () {
            let message = "Unable to load video source.";

            if (video.error) {
                switch (video.error.code) {
                    case MediaError.MEDIA_ERR_ABORTED:
                        message = "Video loading was aborted.";
                        break;
                    case MediaError.MEDIA_ERR_NETWORK:
                        message = "A network error interrupted video loading.";
                        break;
                    case MediaError.MEDIA_ERR_DECODE:
                        message = "The video could not be decoded.";
                        break;
                    case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
                        message = "This video format or codec is not supported.";
                        break;
                }
            }

            showError(message);
        });

        /* ---------- Начальное состояние ---------- */

        updateVolumeUI();
        updateFullscreenUI();
        updatePlayState();

        if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
            updateMetadata();
            updateProgress();
        } else if (video.error) {
            showError("Unable to load video source.");
        }
    }

    function init(root) {
        (root || document).querySelectorAll(SELECTOR).forEach(build);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            init();
        });
    } else {
        init();
    }

    window.AetherVideoWidget = { init: init };
})();