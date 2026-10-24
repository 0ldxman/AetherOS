/* ==================================================
   AETHER OS / AUDIO WIDGET
   Встроенный плеер для .doc--rec и .doc--infobox.
   Берёт <audio controls> из _render_audio и собирает
   плоскую полосу управления в стиле аудио-просмотрщика.
   Без JS остаётся родной плеер браузера.
   ================================================== */

(function () {
    "use strict";

    const SELECTOR = ".doc--rec .widget--audio, .doc--infobox .widget--audio";

    const ICON_PLAY = '<path d="M8 5.5 19 12 8 18.5Z" />';

    const SPEEDS = ["0.5", "0.75", "1", "1.25", "1.5", "2"];

    function template(hasViewer) {
        const speedOptions = SPEEDS.map(function (v) {
            return `<option value="${v}"${v === "1" ? " selected" : ""}>${v}×</option>`;
        }).join("");

        const openButton = hasViewer
            ? `<a class="aw-btn aw-open" title="Open in viewer" aria-label="Open in viewer">
                   <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-8 8M18 14v6H4V6h6" /></svg>
               </a>`
            : "";

        return `
            <div class="aw-head">
                <div class="aw-title">
                    <span class="aw-format"></span>
                    <b class="aw-name"></b>
                </div>
                <div class="aw-status">READY</div>
            </div>

            <div class="aw-info">
                <div class="aw-info-line"><span class="aw-label">ID:</span><span class="aw-value aw-id"></span></div>
                <div class="aw-info-line"><span class="aw-label">DURATION:</span><span class="aw-value aw-dur">—</span></div>
            </div>

            <div class="aw-error" hidden>
                <span>AUDIO / ERROR</span>
                <p></p>
            </div>

            <div class="aw-controls">
                <div class="aw-progress-row">
                    <span class="aw-time aw-cur">00:00</span>
                    <input class="aw-progress" type="range" min="0" max="1000" value="0" step="1" aria-label="Seek audio">
                    <span class="aw-time aw-total">00:00</span>
                </div>

                <div class="aw-row">
                    <div class="aw-group">
                        <button class="aw-btn aw-play" type="button" aria-label="Play" title="Play (Space)">
                            <svg viewBox="0 0 24 24" aria-hidden="true">${ICON_PLAY}</svg>
                        </button>
                        <button class="aw-btn aw-mute" type="button" aria-label="Mute" title="Mute (M)">
                            <svg viewBox="0 0 24 24" aria-hidden="true">
                                <path d="M4 9v6h4l5 4V5L8 9H4Z" />
                                <path class="aw-wave" d="M16 9a4 4 0 0 1 0 6" />
                                <path class="aw-cross" d="m17 9 5 6m0-6-5 6" hidden />
                            </svg>
                        </button>
                        <input class="aw-volume" type="range" min="0" max="1" value="1" step="0.01" aria-label="Volume">
                    </div>

                    <div class="aw-group aw-group-right">
                        <label class="aw-speed">
                            <span>SPEED</span>
                            <select aria-label="Playback speed">${speedOptions}</select>
                        </label>
                        ${openButton}
                    </div>
                </div>
            </div>
        `;
    }

    function build(figure) {
        if (figure.dataset.awReady) {
            return;
        }

        const audio = figure.querySelector("audio.audio-el");

        if (!audio) {
            return;
        }

        figure.dataset.awReady = "1";
        figure.classList.add("aw-ready");

        /* ---------- Каркас ---------- */

        const fileName = figure.dataset.fileName || "";
        const dot = fileName.lastIndexOf(".");
        const extension = dot > 0 ? fileName.slice(dot + 1).toUpperCase() : "UNKNOWN";
        const viewerUrl = figure.dataset.viewerUrl || "";

        const titleNode = figure.querySelector(".audio-title");
        const title = titleNode ? titleNode.textContent.trim() : fileName;

        if (titleNode) {
            titleNode.remove();
        }

        audio.removeAttribute("controls");

        const box = document.createElement("div");
        box.className = "aw-box";
        box.tabIndex = 0;
        box.innerHTML = template(Boolean(viewerUrl));
        figure.insertBefore(box, figure.firstChild);

        const q = function (selector) {
            return box.querySelector(selector);
        };

        const status = q(".aw-status");
        const duration = q(".aw-dur");
        const errorBox = q(".aw-error");
        const errorText = q(".aw-error p");
        const current = q(".aw-cur");
        const total = q(".aw-total");
        const progress = q(".aw-progress");
        const playButton = q(".aw-play");
        const playIcon = q(".aw-play svg");
        const muteButton = q(".aw-mute");
        const wave = q(".aw-wave");
        const cross = q(".aw-cross");
        const volume = q(".aw-volume");
        const speed = q(".aw-speed select");
        const openLink = q(".aw-open");

        q(".aw-format").textContent = `[AUDIO.${extension}]`;
        q(".aw-name").textContent = title;
        q(".aw-id").textContent = figure.dataset.assetId || "—";

        if (openLink && viewerUrl) {
            openLink.setAttribute("href", viewerUrl);
            openLink.setAttribute("data-asset-viewer", viewerUrl);
            openLink.setAttribute("data-asset-title", fileName || title);
            openLink.addEventListener("click", function () {
                audio.pause();
            });
        }

        /* ---------- Метаданные ---------- */

        function updateMetadata() {
            duration.textContent = Aether.formatTime(audio.duration);
        }

        /* ---------- Плеер ---------- */

        const player = Aether.createPlayer(
            audio,
            {
                stage: box,
                status: status,
                playButton: playButton,
                playIcon: playIcon,
                muteButton: muteButton,
                wave: wave,
                cross: cross,
                volume: volume,
                speed: speed,
                progress: progress,
                current: current,
                total: total,
                error: errorBox,
                errorMessage: errorText,
            },
            {
                label: "audio",
                classes: { playing: "aw-playing" },
                progressVar: "--aw-progress",
                onMetadata: updateMetadata,
                onError: function () {
                    box.classList.add("aw-failed");
                },
            }
        );

        /* одновременно звучит только один ассет на странице */
        audio.addEventListener("play", function () {
            document.querySelectorAll("audio, video").forEach(function (media) {
                if (media !== audio) {
                    media.pause();
                }
            });
        });

        /* ---------- Клавиатура ---------- */

        box.addEventListener("keydown", function (event) {
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

        /* в разметке preload="none": нужна только длительность */
        if (
            audio.readyState < HTMLMediaElement.HAVE_METADATA &&
            !audio.error &&
            audio.preload === "none"
        ) {
            audio.preload = "metadata";
            audio.load();
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

    window.AetherAudioWidget = { init: init };
})();