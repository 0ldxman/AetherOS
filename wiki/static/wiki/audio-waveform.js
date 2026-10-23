
/* =========================================================
   Aether Wiki — Scan Audio Waveform
   Статичная осциллограмма для аудиокарточек в сканах.
   AudioContext создаётся только после действия пользователя.
   ========================================================= */

(function () {
    "use strict";

    const SELECTOR = ".doc--scan .audio-card-waveform";
    const BAR_COUNT = 180;
    const SVG_NS = "http://www.w3.org/2000/svg";

    const AudioContextClass =
        window.AudioContext || window.webkitAudioContext;

    let audioContext = null;
    let initialized = false;
    let userActivated = false;

    const pendingContainers = new Set();

    function formatDuration(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) {
            return "—:—";
        }

        seconds = Math.floor(seconds);

        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const remainder = seconds % 60;

        const pad = value => String(value).padStart(2, "0");

        if (hours > 0) {
            return `${hours}:${pad(minutes)}:${pad(remainder)}`;
        }

        return `${minutes}:${pad(remainder)}`;
    }

    function getContext() {
        if (!AudioContextClass) {
            return null;
        }

        if (!audioContext || audioContext.state === "closed") {
            audioContext = new AudioContextClass();
        }

        return audioContext;
    }

    function createSvgElement(name, attributes = {}) {
        const element = document.createElementNS(SVG_NS, name);

        for (const [key, value] of Object.entries(attributes)) {
            element.setAttribute(key, String(value));
        }

        return element;
    }

    function renderWaveform(container, channelData) {
        const svg = container.querySelector(".audio-waveform-svg");

        if (!svg || !channelData.length) {
            return;
        }

        const width = 600;
        const height = 72;
        const center = height / 2;
        const halfHeight = 29;

        const sampleCount = channelData[0].length;

        if (!sampleCount) {
            return;
        }

        const fragment = document.createDocumentFragment();

        fragment.appendChild(
            createSvgElement("line", {
                x1: 0,
                y1: center,
                x2: width,
                y2: center,
                class: "audio-waveform-baseline",
            })
        );

        for (let i = 0; i < BAR_COUNT; i++) {
            const start = Math.floor(i * sampleCount / BAR_COUNT);
            const end = Math.max(
                start + 1,
                Math.floor((i + 1) * sampleCount / BAR_COUNT)
            );

            let peak = 0;

            for (const channel of channelData) {
                const limit = Math.min(end, channel.length);

                for (let sample = start; sample < limit; sample++) {
                    const amplitude = Math.abs(channel[sample]);

                    if (amplitude > peak) {
                        peak = amplitude;
                    }
                }
            }

            const x = (i / BAR_COUNT) * width + 0.5;
            const amplitude = Math.max(0.7, peak * halfHeight);

            fragment.appendChild(
                createSvgElement("line", {
                    x1: x,
                    y1: center - amplitude,
                    x2: x,
                    y2: center + amplitude,
                    class: "audio-waveform-line",
                })
            );
        }

        svg.replaceChildren(fragment);
        container.classList.add("is-ready");
    }

    async function processWaveform(container) {
        if (
            container.dataset.waveformState === "loading" ||
            container.dataset.waveformState === "ready" ||
            container.dataset.waveformState === "failed"
        ) {
            pendingContainers.delete(container);
            return;
        }

        const source = container.dataset.audioSrc;

        if (!source) {
            container.dataset.waveformState = "failed";
            container.classList.add("is-unavailable");
            pendingContainers.delete(container);
            return;
        }

        if (!userActivated) {
            pendingContainers.add(container);
            return;
        }

        container.dataset.waveformState = "loading";

        try {
            const context = getContext();

            if (!context) {
                throw new Error("Web Audio API is unavailable.");
            }

            if (context.state === "suspended") {
                await context.resume();
            }

            const response = await fetch(source, {
                credentials: "same-origin",
            });

            if (!response.ok) {
                throw new Error(
                    `Audio request failed: ${response.status}`
                );
            }

            const buffer = await response.arrayBuffer();
            const audioBuffer = await context.decodeAudioData(buffer);

            const channels = [];

            for (
                let channel = 0;
                channel < audioBuffer.numberOfChannels;
                channel++
            ) {
                channels.push(audioBuffer.getChannelData(channel));
            }

            renderWaveform(container, channels);

            const card = container.closest(".audio-card");
            const duration = card?.querySelector(".audio-duration");

            if (duration) {
                duration.textContent = formatDuration(audioBuffer.duration);
            }

            container.dataset.waveformState = "ready";
        } catch (error) {
            console.warn(
                "[Aether Audio] Could not generate waveform:",
                error
            );

            container.dataset.waveformState = "failed";
            container.classList.add("is-unavailable");
        } finally {
            pendingContainers.delete(container);
        }
    }

    function processPendingWaveforms() {
        if (!userActivated) {
            return;
        }

        for (const container of pendingContainers) {
            processWaveform(container);
        }
    }

    function activateAudio() {
        if (userActivated) {
            return;
        }

        userActivated = true;

        document.removeEventListener("pointerdown", activateAudio, true);
        document.removeEventListener("keydown", activateAudio, true);
        document.removeEventListener("touchstart", activateAudio, true);

        document.querySelectorAll(SELECTOR).forEach(container => {
            if (!container.dataset.waveformState) {
                pendingContainers.add(container);
            }
        });

        processPendingWaveforms();
    }

    function initialize() {
        if (initialized) {
            return;
        }

        initialized = true;

        const containers = document.querySelectorAll(SELECTOR);

        if (!containers.length) {
            return;
        }

        /*
         * Регистрируем действие пользователя.
         * AudioContext здесь не создаётся.
         */
        document.addEventListener("pointerdown", activateAudio, true);
        document.addEventListener("keydown", activateAudio, true);
        document.addEventListener("touchstart", activateAudio, {
            capture: true,
            passive: true,
        });

        if ("IntersectionObserver" in window) {
            const observer = new IntersectionObserver(
                entries => {
                    for (const entry of entries) {
                        if (!entry.isIntersecting) {
                            continue;
                        }

                        observer.unobserve(entry.target);

                        if (userActivated) {
                            processWaveform(entry.target);
                        } else {
                            pendingContainers.add(entry.target);
                        }
                    }
                },
                {
                    rootMargin: "250px 0px",
                }
            );

            containers.forEach(container => {
                observer.observe(container);
            });
        } else {
            containers.forEach(container => {
                pendingContainers.add(container);
            });

            processPendingWaveforms();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialize, {
            once: true,
        });
    } else {
        initialize();
    }
})();
