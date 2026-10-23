
/* =========================================================
   Aether Wiki — Scan Audio
   Архивная аудиозапись с бумажной наклейкой и аудиограммой.
   ========================================================= */

(function () {
    "use strict";

    const SELECTOR = ".doc--scan .widget--audio";
    const initialized = new WeakSet();
    const channelName = "aether-audio-playback";

    let channel = null;

    try {
        if ("BroadcastChannel" in window) {
            channel = new BroadcastChannel(channelName);
        }
    } catch (_) {
        channel = null;
    }

    function formatTime(value) {
        if (!Number.isFinite(value) || value < 0) {
            return "00:00";
        }

        const seconds = Math.floor(value);
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const remainder = seconds % 60;

        const mm = String(minutes).padStart(2, "0");
        const ss = String(remainder).padStart(2, "0");

        return hours > 0
            ? String(hours).padStart(2, "0") + ":" + mm + ":" + ss
            : mm + ":" + ss;
    }

    function notifyPlayback(audio) {
        if (channel) {
            channel.postMessage({ type: "play" });
        }

        document.querySelectorAll(".audio-el, audio").forEach(function (other) {
            if (other !== audio && !other.paused) {
                other.pause();
            }
        });
    }

    if (channel) {
        channel.addEventListener("message", function (event) {
            if (!event.data || event.data.type !== "play") {
                return;
            }

            document.querySelectorAll("audio").forEach(function (audio) {
                if (!audio.paused) {
                    audio.pause();
                }
            });
        });
    }

    function createBars(container, peaks) {
        container.replaceChildren();

        peaks.forEach(function (peak, index) {
            const bar = document.createElement("span");
            bar.className = "audio-wave-bar";
            bar.style.setProperty(
                "--bar-height",
                Math.max(5, Math.round(peak * 100)) + "%"
            );
            bar.dataset.index = String(index);
            container.appendChild(bar);
        });
    }

    function updateWaveform(widget, progress) {
        const bars = widget.querySelectorAll(".audio-wave-bar");
        const current = Math.max(0, Math.min(1, progress));

        bars.forEach(function (bar, index) {
            bar.classList.toggle(
                "is-played",
                index < current * bars.length
            );
        });

        const waveform = widget.querySelector(".audio-waveform");

        if (waveform) {
            waveform.setAttribute(
                "aria-valuenow",
                String(Math.round(current * 100))
            );
        }
    }

    async function extractPeaks(url, count) {
        const response = await fetch(url);

        if (!response.ok) {
            throw new Error("Не удалось загрузить аудиофайл");
        }

        const data = await response.arrayBuffer();
        const AudioContextClass =
            window.AudioContext || window.webkitAudioContext;

        if (!AudioContextClass) {
            throw new Error("Web Audio API недоступен");
        }

        const context = new AudioContextClass();

        try {
            const buffer = await context.decodeAudioData(data);
            const channelData = [];

            for (let i = 0; i < buffer.numberOfChannels; i++) {
                channelData.push(buffer.getChannelData(i));
            }

            const length = buffer.length;
            const blockSize = Math.max(1, Math.floor(length / count));
            const peaks = [];

            for (let i = 0; i < count; i++) {
                const start = i * blockSize;
                const end = i === count - 1
                    ? length
                    : Math.min(length, start + blockSize);

                let peak = 0;

                for (const samples of channelData) {
                    for (let j = start; j < end; j++) {
                        peak = Math.max(peak, Math.abs(samples[j]));
                    }
                }

                peaks.push(peak);
            }

            return {
                peaks: peaks,
                duration: buffer.duration
            };
        } finally {
            await context.close();
        }
    }

    function initWidget(widget) {
        if (initialized.has(widget)) {
            return;
        }

        initialized.add(widget);

        const audio = widget.querySelector(".audio-el");
        const playButton = widget.querySelector(".audio-play");
        const waveform = widget.querySelector(".audio-waveform");
        const barsContainer = widget.querySelector(".audio-waveform-bars");
        const currentTime = widget.querySelector(".audio-current-time");
        const durationLabel = widget.querySelector(".audio-duration");

        if (
            !audio ||
            !playButton ||
            !waveform ||
            !barsContainer
        ) {
            return;
        }

        let duration = 0;

        audio.addEventListener("loadedmetadata", function () {
            if (Number.isFinite(audio.duration)) {
                duration = audio.duration;
                durationLabel.textContent = formatTime(duration);
            }

            playButton.disabled = false;
        });

        audio.addEventListener("timeupdate", function () {
            currentTime.textContent = formatTime(audio.currentTime);

            if (duration > 0) {
                updateWaveform(widget, audio.currentTime / duration);
            }
        });

        audio.addEventListener("play", function () {
            notifyPlayback(audio);
            playButton.textContent = "PAUSE";
            playButton.setAttribute("aria-label", "Пауза");
        });

        audio.addEventListener("pause", function () {
            playButton.textContent = "PLAY";
            playButton.setAttribute("aria-label", "Воспроизвести");
        });

        audio.addEventListener("ended", function () {
            updateWaveform(widget, 0);
            currentTime.textContent = "00:00";
        });

        audio.addEventListener("error", function () {
            widget.classList.add("audio--failed");
            playButton.disabled = true;
        });

        playButton.addEventListener("click", async function () {
            if (audio.paused) {
                try {
                    notifyPlayback(audio);
                    await audio.play();
                } catch (error) {
                    widget.classList.add("audio--failed");
                    console.warn(
                        "[Aether Wiki] Не удалось воспроизвести аудио:",
                        error
                    );
                }
            } else {
                audio.pause();
            }
        });

        function seekToPosition(event) {
            if (!duration) {
                return;
            }

            const rect = waveform.getBoundingClientRect();
            const progress = Math.max(
                0,
                Math.min(1, (event.clientX - rect.left) / rect.width)
            );

            audio.currentTime = progress * duration;
            updateWaveform(widget, progress);
        }

        waveform.addEventListener("click", seekToPosition);

        waveform.addEventListener("keydown", function (event) {
            if (!duration) {
                return;
            }

            let target = audio.currentTime;

            if (event.key === "ArrowRight") {
                target += 5;
            } else if (event.key === "ArrowLeft") {
                target -= 5;
            } else if (event.key === "Home") {
                target = 0;
            } else if (event.key === "End") {
                target = duration;
            } else {
                return;
            }

            event.preventDefault();
            audio.currentTime = Math.max(0, Math.min(duration, target));
        });

        /*
         * Форма волны не должна блокировать воспроизведение.
         * Если браузер не смог декодировать данные для анализа,
         * аудио всё ещё может воспроизводиться обычным способом.
         */
        extractPeaks(audio.currentSrc || audio.src, 120)
            .then(function (result) {
                createBars(barsContainer, result.peaks);

                if (!duration) {
                    duration = result.duration;
                    durationLabel.textContent = formatTime(duration);
                }

                updateWaveform(
                    widget,
                    duration > 0 ? audio.currentTime / duration : 0
                );
            })
            .catch(function (error) {
                widget.classList.add("audio--waveform-unavailable");

                console.warn(
                    "[Aether Wiki] Не удалось построить аудиограмму:",
                    audio.currentSrc || audio.src,
                    error
                );
            });
    }

    function scan(root) {
        if (!root || !root.querySelectorAll) {
            return;
        }

        if (root.matches && root.matches(SELECTOR)) {
            initWidget(root);
        }

        root.querySelectorAll(SELECTOR).forEach(initWidget);
    }

    function init() {
        scan(document);

        const observer = new MutationObserver(function (records) {
            records.forEach(function (record) {
                record.addedNodes.forEach(function (node) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        scan(node);
                    }
                });
            });
        });

        observer.observe(document.documentElement, {
            childList: true,
            subtree: true
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, { once: true });
    } else {
        init();
    }
})();
