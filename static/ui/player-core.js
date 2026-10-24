/* ==================================================
   AETHER OS / PLAYER CORE
   Общая логика плееров: вьюверов ассетов и вики-виджетов
   (сейчас видео). Разметка и стили остаются на стороне вызывающего:
   ядро только управляет <video>/<audio> и переданными элементами.

   Aether.createPlayer(media, ui, options) -> api

   ui (все поля, кроме media-управления, необязательны):
     stage          контейнер: получает классы состояния
     controls       панель управления (не прячем, пока на ней курсор)
     status         текст статуса
     playButton, playIcon, center (большая кнопка Play, hidden при игре)
     muteButton, wave, cross, volume, speed (select), fullscreenButton
     progress (range 0..1000), current, total (метки времени)
     loading, error, errorMessage
   options:
     label          "video" | "audio": для текстов ошибок
     classes        { playing, hidden }: классы на stage
     progressVar    CSS-переменная заливки прогресса, например "--vv-progress"
     fullscreenTarget  что раскрывать (по умолчанию stage)
     fullscreenClass   класс на stage в полноэкранном режиме
     hoverGuards    элементы, над которыми панель не прячется
     onMetadata     вызывается при каждом обновлении метаданных
     onError        вызывается с текстом ошибки (после показа ошибки)
     beforePlay     async-функция перед media.play() (например, resume AudioContext)
     volumeModel    { get(), isMuted(), setVolume(v), setMuted(m) }: если громкость
                    живёт не в самом элементе (Web Audio). По умолчанию media.volume/muted
   ================================================== */

(function () {
    "use strict";

    const Aether = (window.Aether = window.Aether || {});

    const AUTO_HIDE_DELAY = 2200;
    const SEEK_STEP = 5;

    const ICON_PLAY = '<path d="M8 5.5 19 12 8 18.5Z" />';
    const ICON_PAUSE = '<path d="M7 5h4v14H7zM15 5h4v14h-4z" />';

    function errorMessage(media, label) {
        const noun = label.charAt(0).toUpperCase() + label.slice(1);
        const code = media.error && media.error.code;

        switch (code) {
            case MediaError.MEDIA_ERR_ABORTED:
                return `${noun} loading was aborted.`;
            case MediaError.MEDIA_ERR_NETWORK:
                return `A network error interrupted ${label} loading.`;
            case MediaError.MEDIA_ERR_DECODE:
                return `The ${label} could not be decoded.`;
            case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
                return `This ${label} format or codec is not supported.`;
            default:
                return `Unable to load ${label} source.`;
        }
    }

    Aether.createPlayer = function (media, ui, options) {
        options = options || {};

        const label = options.label || "video";
        const classes = options.classes || {};
        const stage = ui.stage || null;
        const fullscreenTarget = options.fullscreenTarget || stage;
        const hoverGuards = [ui.controls].concat(options.hoverGuards || []).filter(Boolean);
        const on = function (element, type, handler) {
            if (element) {
                element.addEventListener(type, handler);
            }
        };

        let hideTimer = null;
        let seeking = false;
        let failed = false;

        const volumeModel = options.volumeModel || {
            get: function () {
                return media.volume;
            },
            isMuted: function () {
                return media.muted;
            },
            setVolume: function (value) {
                media.volume = value;
            },
            setMuted: function (value) {
                media.muted = value;
            },
        };

        /* ---------- Состояние ---------- */

        function setStatus(value) {
            if (ui.status) {
                ui.status.textContent = value;
            }
        }

        function showControls() {
            clearTimeout(hideTimer);

            if (stage && classes.hidden) {
                stage.classList.remove(classes.hidden);
            }
        }

        function scheduleHide() {
            clearTimeout(hideTimer);

            if (media.paused || media.ended || failed || seeking || !stage || !classes.hidden) {
                showControls();
                return;
            }

            hideTimer = setTimeout(function () {
                const hovered = hoverGuards.some(function (el) {
                    return el.matches(":hover");
                });

                if (!hovered) {
                    stage.classList.add(classes.hidden);
                }
            }, AUTO_HIDE_DELAY);
        }

        function showError(message) {
            failed = true;
            showControls();

            if (ui.loading) {
                ui.loading.hidden = true;
            }

            if (ui.error) {
                ui.error.hidden = false;
            }

            if (ui.errorMessage) {
                ui.errorMessage.textContent = message || errorMessage(media, label);
            }

            if (ui.center) {
                ui.center.hidden = true;
            }

            setStatus("ERROR");

            if (options.onError) {
                options.onError(message || errorMessage(media, label));
            }
        }

        function hideLoading() {
            if (ui.loading) {
                ui.loading.hidden = true;
            }
        }

        /* ---------- Метаданные ---------- */

        function updateMetadata() {
            if (ui.total) {
                ui.total.textContent = Aether.formatTime(media.duration);
            }

            if (options.onMetadata) {
                options.onMetadata(media);
            }
        }

        /* ---------- Воспроизведение ---------- */

        function updatePlayState() {
            const playing = !media.paused && !media.ended;

            if (stage && classes.playing) {
                stage.classList.toggle(classes.playing, playing);
            }

            if (ui.playButton) {
                ui.playButton.setAttribute("aria-label", playing ? "Pause" : "Play");
                ui.playButton.title = playing ? "Pause (Space)" : "Play (Space)";
            }

            if (ui.playIcon) {
                ui.playIcon.innerHTML = playing ? ICON_PAUSE : ICON_PLAY;
            }

            if (ui.center) {
                ui.center.hidden = playing || failed;
            }

            if (failed) {
                setStatus("ERROR");
            } else if (media.ended) {
                setStatus("END OF FILE");
            } else if (playing) {
                setStatus("PLAYING");
            } else if (media.currentTime > 0) {
                setStatus("PAUSED");
            } else {
                setStatus("READY");
            }
        }

        async function togglePlayback() {
            if (failed) {
                return;
            }

            if (media.paused || media.ended) {
                if (media.ended) {
                    media.currentTime = 0;
                }

                try {
                    if (options.beforePlay) {
                        await options.beforePlay();
                    }

                    await media.play();
                } catch (err) {
                    showError(
                        "Playback could not be started. The format may not be supported by this browser."
                    );
                }
            } else {
                media.pause();
            }

            showControls();
        }

        function seekBy(seconds) {
            const target = media.currentTime + seconds;

            media.currentTime = Number.isFinite(media.duration)
                ? Math.max(0, Math.min(media.duration, target))
                : Math.max(0, target);
        }

        /* ---------- Таймлайн ---------- */

        function paintProgress(fraction) {
            if (ui.progress && options.progressVar) {
                ui.progress.style.setProperty(options.progressVar, `${fraction * 100}%`);
            }
        }

        function updateProgress() {
            if (ui.current) {
                ui.current.textContent = Aether.formatTime(media.currentTime);
            }

            if (ui.progress && !seeking && Number.isFinite(media.duration) && media.duration > 0) {
                const value = Math.round((media.currentTime / media.duration) * 1000);

                ui.progress.value = String(value);
                paintProgress(value / 1000);
            }
        }

        function seekFromSlider() {
            if (!Number.isFinite(media.duration) || media.duration <= 0) {
                return;
            }

            const fraction = Number(ui.progress.value) / 1000;

            media.currentTime = fraction * media.duration;
            paintProgress(fraction);

            if (ui.current) {
                ui.current.textContent = Aether.formatTime(media.currentTime);
            }
        }

        function endSeek() {
            if (seeking) {
                seekFromSlider();
                seeking = false;
                scheduleHide();
            }
        }

        /* ---------- Громкость ---------- */

        function updateVolumeUI() {
            const silent = volumeModel.isMuted() || volumeModel.get() === 0;

            if (ui.volume) {
                ui.volume.value = String(silent ? 0 : volumeModel.get());
            }

            if (ui.muteButton) {
                ui.muteButton.setAttribute("aria-label", silent ? "Unmute" : "Mute");
            }

            if (ui.wave) {
                ui.wave.hidden = silent;
            }

            if (ui.cross) {
                ui.cross.hidden = !silent;
            }
        }

        function toggleMute() {
            volumeModel.setMuted(!volumeModel.isMuted());
            updateVolumeUI();
        }

        /* ---------- Полный экран ---------- */

        function isFullscreen() {
            return Boolean(fullscreenTarget) && document.fullscreenElement === fullscreenTarget;
        }

        function updateFullscreenUI() {
            const active = isFullscreen();

            if (stage && options.fullscreenClass) {
                stage.classList.toggle(options.fullscreenClass, active);
            }

            if (ui.fullscreenButton) {
                ui.fullscreenButton.setAttribute(
                    "aria-label",
                    active ? "Exit fullscreen" : "Enter fullscreen"
                );
                ui.fullscreenButton.title = active ? "Exit fullscreen (F)" : "Fullscreen (F)";
            }
        }

        async function toggleFullscreen() {
            if (fullscreenTarget) {
                await Aether.toggleFullscreen(fullscreenTarget, media);
            }

            updateFullscreenUI();
            showControls();
        }

        /* ---------- Клавиатура ---------- */

        /**
         * Выполняет горячую клавишу плеера. Возвращает true, если клавиша
         * обработана. Какие цели события пропускать (поля ввода и т.п.) и где
         * слушать keydown, решает вызывающий.
         */
        function handleKey(event) {
            switch (event.key.toLowerCase()) {
                case " ":
                    event.preventDefault();
                    togglePlayback();
                    break;

                case "arrowleft":
                    event.preventDefault();
                    seekBy(-SEEK_STEP);
                    break;

                case "arrowright":
                    event.preventDefault();
                    seekBy(SEEK_STEP);
                    break;

                case "m":
                    toggleMute();
                    break;

                case "f":
                    if (!fullscreenTarget) {
                        return false;
                    }
                    toggleFullscreen();
                    break;

                default:
                    return false;
            }

            showControls();
            scheduleHide();
            return true;
        }

        /* ---------- Подписки ---------- */

        on(ui.playButton, "click", function (event) {
            event.stopPropagation();
            togglePlayback();
        });

        on(ui.center, "click", function (event) {
            event.stopPropagation();
            togglePlayback();
        });

        on(ui.muteButton, "click", function (event) {
            event.stopPropagation();
            toggleMute();
            showControls();
        });

        on(ui.volume, "input", function () {
            const value = Number(ui.volume.value);

            volumeModel.setVolume(value);
            volumeModel.setMuted(value === 0);
            updateVolumeUI();
            showControls();
        });

        on(ui.speed, "change", function () {
            media.playbackRate = Number(ui.speed.value);
            showControls();
        });

        on(ui.fullscreenButton, "click", function (event) {
            event.stopPropagation();
            toggleFullscreen();
        });

        on(ui.progress, "pointerdown", function () {
            seeking = true;
            showControls();
        });

        on(ui.progress, "input", function () {
            const fraction = Number(ui.progress.value) / 1000;

            paintProgress(fraction);

            if (ui.current && Number.isFinite(media.duration) && media.duration > 0) {
                ui.current.textContent = Aether.formatTime(fraction * media.duration);
            }
        });

        on(ui.progress, "change", endSeek);
        on(ui.progress, "pointerup", endSeek);

        on(stage, "pointermove", function () {
            showControls();
            scheduleHide();
        });

        on(stage, "pointerleave", scheduleHide);
        on(ui.controls, "pointerenter", showControls);
        on(ui.controls, "pointerleave", scheduleHide);

        options.hoverGuards && options.hoverGuards.forEach(function (el) {
            on(el, "pointerenter", showControls);
        });

        media.addEventListener("click", togglePlayback);

        media.addEventListener("play", function () {
            updatePlayState();
            scheduleHide();
        });

        media.addEventListener("playing", function () {
            updatePlayState();
            scheduleHide();
        });

        media.addEventListener("pause", function () {
            updatePlayState();
            showControls();
        });

        media.addEventListener("ended", function () {
            updatePlayState();
            showControls();
        });

        media.addEventListener("waiting", function () {
            if (!media.paused) {
                setStatus("BUFFERING");
            }
        });

        media.addEventListener("timeupdate", updateProgress);
        media.addEventListener("durationchange", updateMetadata);
        media.addEventListener("volumechange", updateVolumeUI);
        document.addEventListener("fullscreenchange", updateFullscreenUI);

        media.addEventListener("loadedmetadata", function () {
            hideLoading();
            updateMetadata();
            updateProgress();
            updatePlayState();
        });

        media.addEventListener("canplay", hideLoading);

        media.addEventListener("error", function () {
            showError(errorMessage(media, label));
        });

        /* ---------- Начальное состояние ---------- */

        updateVolumeUI();
        updateFullscreenUI();
        updatePlayState();

        if (media.readyState >= HTMLMediaElement.HAVE_METADATA) {
            hideLoading();
            updateMetadata();
            updateProgress();
        } else if (media.error) {
            showError(errorMessage(media, label));
        }

        return {
            togglePlayback: togglePlayback,
            toggleFullscreen: toggleFullscreen,
            toggleMute: toggleMute,
            seekBy: seekBy,
            handleKey: handleKey,
            showControls: showControls,
            scheduleHide: scheduleHide,
            setStatus: setStatus,
        };
    };
})();
