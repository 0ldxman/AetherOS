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
    const ICON_PLAY = '<path d="M8 5.5 19 12 8 18.5Z" />';

    const SPEEDS = ["0.5", "0.75", "1", "1.25", "1.5", "2"];

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
        const controls = q(".vw-controls");
        const status = q(".vw-status");
        const resolution = q(".vw-res");
        const duration = q(".vw-dur");
        const current = q(".vw-cur");
        const total = q(".vw-total");
        const progress = q(".vw-progress");
        const playButton = q(".vw-play");
        const playIcon = q(".vw-play svg");
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

        /* ---------- Метаданные ---------- */

        function updateMetadata() {
            if (video.videoWidth && video.videoHeight) {
                resolution.textContent = `${video.videoWidth} × ${video.videoHeight}`;
                stage.style.setProperty(
                    "--vw-ratio",
                    `${video.videoWidth} / ${video.videoHeight}`
                );
            }

            duration.textContent = Aether.formatTime(video.duration);
        }

        /* ---------- Плеер ---------- */

        const player = Aether.createPlayer(
            video,
            {
                stage: stage,
                controls: controls,
                status: status,
                center: center,
                playButton: playButton,
                playIcon: playIcon,
                muteButton: muteButton,
                wave: wave,
                cross: cross,
                volume: volume,
                speed: speed,
                fullscreenButton: fsButton,
                progress: progress,
                current: current,
                total: total,
                error: errorBox,
                errorMessage: errorText,
            },
            {
                label: "video",
                classes: { playing: "vw-playing", hidden: "vw-hidden" },
                progressVar: "--vw-progress",
                fullscreenClass: "vw-fullscreen",
                onMetadata: updateMetadata,
            }
        );

        /* ---------- Клавиатура ---------- */

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

            player.handleKey(event);
        });
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