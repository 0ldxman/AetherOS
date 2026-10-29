
/* =========================================================
   Aether Wiki — Scan Audio Waveform

   1. Мгновенная детерминированная декоративная волна.
   2. Отложенная загрузка и декодирование аудио.
   3. Плавная замена декоративной формы настоящей.
   4. Кэширование амплитуд в памяти и sessionStorage.
   ========================================================= */

(function () {
    "use strict";

    const SELECTOR = ".doc--scan .audio-card-waveform";
    const BAR_COUNT = 180;

    const SVG_WIDTH = 600;
    const SVG_HEIGHT = 72;
    const CENTER_Y = SVG_HEIGHT / 2;

    const MAX_AMPLITUDE = 29;
    const MIN_AMPLITUDE = 1.2;

    const TRANSITION_MS = 700;
    const MAX_CONCURRENT = 2;

    const CACHE_PREFIX = "aether-audio-waveform-v2:";

    const SVG_NS = "http://www.w3.org/2000/svg";

    const memoryCache = new Map();
    const queue = [];
    const queued = new WeakSet();
    const completed = new WeakSet();

    let activeJobs = 0;
    let audioContext = null;
    let intersectionObserver = null;

    /* -----------------------------------------------------
       Utilities
       ----------------------------------------------------- */

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function hashString(value) {
        let hash = 2166136261;

        for (let i = 0; i < value.length; i++) {
            hash ^= value.charCodeAt(i);
            hash = Math.imul(hash, 16777619);
        }

        return hash >>> 0;
    }

    function createRandom(seed) {
        let state = seed >>> 0;

        return function () {
            state += 0x6D2B79F5;

            let value = state;
            value = Math.imul(value ^ (value >>> 15), value | 1);
            value ^= value + Math.imul(
                value ^ (value >>> 7),
                value | 61
            );

            return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
        };
    }

    function getAudioSource(container) {
        return (container.dataset.audioSrc || "").trim();
    }

    function getCardMetadata(container) {
        const card = container.closest(".audio-card");

        const titleElement = card
            ? card.querySelector(".audio-card-field--title")
            : null;

        const metaElement = card
            ? card.querySelector(".audio-card-meta")
            : null;

        const title = titleElement
            ? titleElement.textContent.trim()
            : "";

        const metadata = metaElement
            ? metaElement.textContent.trim()
            : "";

        const durationElement = card
            ? card.querySelector(".audio-duration")
            : null;

        const durationText = durationElement
            ? durationElement.textContent.trim()
            : "";

        const duration = parseDuration(durationText || metadata);

        return {
            title,
            metadata,
            duration
        };
    }

    function parseDuration(text) {
        if (!text) {
            return 0;
        }

        const matches = text.match(
            /(?:^|\D)(\d{1,3}):([0-5]\d)(?::([0-5]\d))?(?:\D|$)/
        );

        if (!matches) {
            return 0;
        }

        if (matches[3] !== undefined) {
            return (
                Number(matches[1]) * 3600 +
                Number(matches[2]) * 60 +
                Number(matches[3])
            );
        }

        return Number(matches[1]) * 60 + Number(matches[2]);
    }


    function formatDuration(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) {
            return "—:—";
        }

        const total = Math.floor(seconds);
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const secs = total % 60;

        if (hours > 0) {
            return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
        }

        return `${minutes}:${String(secs).padStart(2, "0")}`;
    }

    function loadDurationMetadata(container) {
        const source = getAudioSource(container);
        const durationElement = container
            .closest(".audio-card")
            ?.querySelector(".audio-duration");

        if (!source || !durationElement) {
            return;
        }

        // Не создаём повторные запросы для одной карточки.
        if (container.dataset.durationRequested === "true") {
            return;
        }

        container.dataset.durationRequested = "true";

        const audio = new Audio();
        audio.preload = "metadata";

        audio.addEventListener("loadedmetadata", () => {
            if (Number.isFinite(audio.duration)) {
                durationElement.textContent = formatDuration(audio.duration);
            }

            audio.removeAttribute("src");
            audio.load();
        }, { once: true });

        audio.addEventListener("error", () => {
            container.dataset.durationError = "true";
        }, { once: true });

        audio.src = source;
    }


    function getCacheKey(container) {
        const source = getAudioSource(container);
        const metadata = getCardMetadata(container);

        return CACHE_PREFIX + hashString([
            source,
            metadata.title,
            metadata.metadata,
            metadata.duration,
            BAR_COUNT
        ].join("|")).toString(16);
    }

    /* -----------------------------------------------------
       SVG
       ----------------------------------------------------- */

    function createSvgElement(name, attributes) {
        const element = document.createElementNS(SVG_NS, name);

        for (const [key, value] of Object.entries(attributes || {})) {
            element.setAttribute(key, String(value));
        }

        return element;
    }

    function getOrCreateSvg(container) {
        let svg = container.querySelector(".audio-waveform-svg");

        if (!svg) {
            svg = createSvgElement("svg", {
                class: "audio-waveform-svg",
                viewBox: `0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`,
                preserveAspectRatio: "none",
                "aria-hidden": "true"
            });

            container.appendChild(svg);
        }

        return svg;
    }

    function createWaveform(container) {
        const svg = getOrCreateSvg(container);

        if (svg.dataset.waveformInitialized === "true") {
            return svg;
        }

        svg.replaceChildren();

        const spacing = SVG_WIDTH / BAR_COUNT;
        const lines = [];

        for (let i = 0; i < BAR_COUNT; i++) {
            const x = (i + 0.5) * spacing;

            const line = createSvgElement("line", {
                class: "audio-waveform-line",
                x1: x.toFixed(2),
                x2: x.toFixed(2),
                y1: CENTER_Y,
                y2: CENTER_Y,
                "vector-effect": "non-scaling-stroke"
            });

            svg.appendChild(line);
            lines.push(line);
        }

        const baseline = createSvgElement("line", {
            class: "audio-waveform-baseline",
            x1: 0,
            x2: SVG_WIDTH,
            y1: CENTER_Y,
            y2: CENTER_Y
        });

        svg.appendChild(baseline);

        svg._waveformLines = lines;
        svg._waveformHeights = new Array(BAR_COUNT).fill(0);

        svg.dataset.waveformInitialized = "true";

        return svg;
    }

    /* -----------------------------------------------------
       Deterministic placeholder waveform
       ----------------------------------------------------- */

    function generatePlaceholder(container) {
        const source = getAudioSource(container);
        const metadata = getCardMetadata(container);

        const seed = hashString([
            source,
            metadata.title,
            metadata.metadata,
            metadata.duration,
            BAR_COUNT
        ].join("|"));

        const random = createRandom(seed);

        const result = [];

        // Случайные опорные точки формируют общий профиль сигнала.
        const anchorCount = 12;
        const anchors = [];

        for (let i = 0; i < anchorCount; i++) {
            anchors.push(
                0.12 + Math.pow(random(), 0.8) * 0.88
            );
        }

        const durationFactor = metadata.duration > 0
            ? clamp(Math.log10(metadata.duration + 1) / 2, 0.2, 1)
            : 0.65;

        // Медленно меняющаяся огибающая.
        for (let i = 0; i < BAR_COUNT; i++) {
            const position = i / (BAR_COUNT - 1);
            const anchorPosition = position * (anchorCount - 1);

            const leftIndex = Math.floor(anchorPosition);
            const rightIndex = Math.min(
                anchorCount - 1,
                leftIndex + 1
            );

            const blend = anchorPosition - leftIndex;

            const envelope =
                anchors[leftIndex] * (1 - blend) +
                anchors[rightIndex] * blend;

            // Локальные изменения делают волну менее искусственной.
            const localVariation = 0.25 + random() * 0.75;

            // Небольшие провалы и участки низкой активности.
            const silenceChance = random();
            const silenceFactor = silenceChance < 0.08
                ? 0.12 + random() * 0.2
                : 1;

            const texture = 0.65 + random() * 0.7;

            let amplitude =
                envelope *
                localVariation *
                texture *
                silenceFactor;

            // Длительность влияет на общий характер рисунка.
            amplitude *= 0.65 + durationFactor * 0.35;

            result.push(clamp(amplitude, 0.025, 1));
        }

        return normalizePeaks(result);
    }

    /* -----------------------------------------------------
       Peak normalization
       ----------------------------------------------------- */

    function normalizePeaks(peaks) {
        let maximum = 0;

        for (const value of peaks) {
            if (Number.isFinite(value)) {
                maximum = Math.max(maximum, value);
            }
        }

        if (maximum <= 0) {
            return peaks.map(() => 0.04);
        }

        return peaks.map(value => {
            const normalized = clamp(value / maximum, 0, 1);

            // Сжатие динамики делает тихие фрагменты заметнее.
            return Math.pow(normalized, 0.72);
        });
    }

    function amplitudeToHeight(value) {
        return MIN_AMPLITUDE +
            clamp(value, 0, 1) * (MAX_AMPLITUDE - MIN_AMPLITUDE);
    }

    /* -----------------------------------------------------
       Rendering and transitions
       ----------------------------------------------------- */

    function renderHeights(svg, heights) {
        const lines = svg._waveformLines;

        if (!lines) {
            return;
        }

        for (let i = 0; i < lines.length; i++) {
            const height = clamp(
                heights[i] || MIN_AMPLITUDE,
                MIN_AMPLITUDE,
                MAX_AMPLITUDE
            );

            lines[i].setAttribute(
                "y1",
                (CENTER_Y - height).toFixed(2)
            );

            lines[i].setAttribute(
                "y2",
                (CENTER_Y + height).toFixed(2)
            );
        }

        svg._waveformHeights = heights.slice();
    }

    function renderPlaceholder(container) {
        const svg = createWaveform(container);

        if (svg.dataset.waveformState === "ready") {
            return;
        }

        if (svg.dataset.waveformState === "placeholder") {
            return;
        }

        const peaks = generatePlaceholder(container);
        const heights = peaks.map(amplitudeToHeight);

        renderHeights(svg, heights);

        svg.dataset.waveformState = "placeholder";
        container.dataset.waveformState = "placeholder";
    }

    function transitionToReal(container, peaks) {
        const svg = createWaveform(container);

        if (!svg._waveformLines) {
            return;
        }

        const startHeights = svg._waveformHeights.slice();
        const targetHeights = peaks.map(amplitudeToHeight);

        if (
            svg.dataset.waveformState === "ready" &&
            startHeights.length === targetHeights.length
        ) {
            return;
        }

        const startTime = performance.now();

        svg.dataset.waveformState = "transitioning";
        container.dataset.waveformState = "transitioning";

        function animate(now) {
            // Если карточку удалили или SVG заменили — прекращаем анимацию.
            if (!svg.isConnected || !svg._waveformLines) {
                return;
            }

            const progress = clamp(
                (now - startTime) / TRANSITION_MS,
                0,
                1
            );

            // Smoothstep: плавное начало и завершение перехода.
            const eased = progress * progress * (3 - 2 * progress);

            const currentHeights = startHeights.map((start, index) => {
                const target = targetHeights[index];

                return start + (target - start) * eased;
            });

            renderHeights(svg, currentHeights);

            if (progress < 1) {
                requestAnimationFrame(animate);
                return;
            }

            renderHeights(svg, targetHeights);

            svg.dataset.waveformState = "ready";
            container.dataset.waveformState = "ready";
        }

        requestAnimationFrame(animate);
    }

    /* -----------------------------------------------------
       Persistent cache
       ----------------------------------------------------- */

    function readCache(key) {
        if (memoryCache.has(key)) {
            return memoryCache.get(key);
        }

        try {
            const raw = sessionStorage.getItem(key);

            if (!raw) {
                return null;
            }

            const parsed = JSON.parse(raw);

            if (
                !Array.isArray(parsed) ||
                parsed.length !== BAR_COUNT ||
                !parsed.every(value =>
                    Number.isFinite(value) && value >= 0 && value <= 1
                )
            ) {
                sessionStorage.removeItem(key);
                return null;
            }

            memoryCache.set(key, parsed);

            return parsed;
        } catch (_) {
            // Хранилище может быть недоступно в приватном режиме.
            return null;
        }
    }

    function writeCache(key, peaks) {
        memoryCache.set(key, peaks);

        try {
            sessionStorage.setItem(key, JSON.stringify(peaks));
        } catch (_) {
            // Переполнение или запрет хранилища не должен ломать UI.
        }
    }

    /* -----------------------------------------------------
       Audio decoding
       ----------------------------------------------------- */

    function getAudioContext() {
        if (audioContext) {
            return audioContext;
        }

        const AudioContextClass =
            window.AudioContext || window.webkitAudioContext;

        if (!AudioContextClass) {
            return null;
        }

        try {
            // Для декодирования не запускаем воспроизведение
            // и не вызываем resume().
            audioContext = new AudioContextClass();

            return audioContext;
        } catch (_) {
            return null;
        }
    }

    function extractPeaks(audioBuffer) {
        const channelCount = audioBuffer.numberOfChannels;
        const length = audioBuffer.length;

        if (!channelCount || !length) {
            throw new Error("Empty audio buffer");
        }

        const peaks = new Array(BAR_COUNT).fill(0);

        for (let bar = 0; bar < BAR_COUNT; bar++) {
            const start = Math.floor(bar * length / BAR_COUNT);
            const end = Math.max(
                start + 1,
                Math.floor((bar + 1) * length / BAR_COUNT)
            );

            let maximum = 0;

            for (let channel = 0; channel < channelCount; channel++) {
                const samples = audioBuffer.getChannelData(channel);

                for (let i = start; i < Math.min(end, length); i++) {
                    const sample = Math.abs(samples[i]);

                    if (sample > maximum) {
                        maximum = sample;
                    }
                }
            }

            peaks[bar] = maximum;
        }

        return normalizePeaks(peaks);
    }

    async function decodeAudio(source) {
        const context = getAudioContext();

        if (!context) {
            throw new Error("AudioContext is unavailable");
        }

        const response = await fetch(source);

        if (!response.ok) {
            throw new Error(
                `Audio request failed: ${response.status}`
            );
        }

        const contentType = response.headers.get("content-type") || "";

        if (contentType.includes("text/html")) {
            throw new Error("Audio URL returned HTML instead of audio");
        }

        const buffer = await response.arrayBuffer();

        if (!buffer.byteLength) {
            throw new Error("Empty audio response");
        }

        const audioBuffer = await context.decodeAudioData(buffer);

        return extractPeaks(audioBuffer);
    }

    /* -----------------------------------------------------
       Queue: limit concurrent downloads / decodes
       ----------------------------------------------------- */

    function enqueue(container) {
        if (
            queued.has(container) ||
            completed.has(container) ||
            !getAudioSource(container)
        ) {
            return;
        }

        queued.add(container);
        queue.push(container);

        processQueue();
    }

    function processQueue() {
        while (
            activeJobs < MAX_CONCURRENT &&
            queue.length > 0
        ) {
            const container = queue.shift();

            if (!container.isConnected) {
                continue;
            }

            activeJobs++;

            processContainer(container)
                .catch(() => {
                    // Декоративная волна остаётся при любой ошибке.
                })
                .finally(() => {
                    activeJobs--;
                    processQueue();
                });
        }
    }

    async function processContainer(container) {
        const source = getAudioSource(container);

        if (!source || !container.isConnected) {
            return;
        }

        const cacheKey = getCacheKey(container);
        const cachedPeaks = readCache(cacheKey);

        if (cachedPeaks) {
            transitionToReal(container, cachedPeaks);
            completed.add(container);
            return;
        }

        try {
            const peaks = await decodeAudio(source);

            if (!container.isConnected) {
                return;
            }

            writeCache(cacheKey, peaks);
            transitionToReal(container, peaks);
        } catch (error) {
            // Не удаляем placeholder: карточка остаётся рабочей.
            container.dataset.waveformError = "true";

            console.warn(
                "[Aether Wiki] Не удалось построить аудиоволну:",
                source,
                error
            );
        } finally {
            completed.add(container);
        }
    }

    /* -----------------------------------------------------
       Initialization
       ----------------------------------------------------- */

    function initializeContainer(container) {
        if (container.dataset.waveformInitialized === "true") {
            return;
        }

        container.dataset.waveformInitialized = "true";

        // Первый кадр всегда декоративный и не ждёт сеть.
        renderPlaceholder(container);

        if (!getAudioSource(container)) {
            return;
        }

        loadDurationMetadata(container);

        const cacheKey = getCacheKey(container);
        const cachedPeaks = readCache(cacheKey);

        if (cachedPeaks) {
            transitionToReal(container, cachedPeaks);
            completed.add(container);
            return;
        }

        if (intersectionObserver) {
            intersectionObserver.observe(container);
        } else {
            enqueue(container);
        }
    }

    function init() {
        if ("IntersectionObserver" in window) {
            intersectionObserver = new IntersectionObserver(
                entries => {
                    for (const entry of entries) {
                        if (!entry.isIntersecting) {
                            continue;
                        }

                        intersectionObserver.unobserve(entry.target);
                        enqueue(entry.target);
                    }
                },
                {
                    root: null,
                    rootMargin: "250px 0px",
                    threshold: 0
                }
            );
        }

        document.querySelectorAll(SELECTOR).forEach(
            initializeContainer
        );
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, {
            once: true
        });
    } else {
        init();
    }
})();
