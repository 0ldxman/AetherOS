/* ==================================================
   AETHER OS / AUDIO VIEWER
   Live loudness graph; playback and controls come from the
   shared player core (static/ui/player-core.js)
   ================================================== */

(function () {
    "use strict";

    const root = document.querySelector("[data-audio-viewer]");

    if (!root) {
        return;
    }

    /* --------------------------------------------------
       Elements
       -------------------------------------------------- */

    const audio = root.querySelector("[data-audio-source]");
    const canvas = root.querySelector("[data-audio-canvas]");
    const context2d = canvas.getContext("2d");

    const loading = root.querySelector("[data-audio-loading]");
    const error = root.querySelector("[data-audio-error]");
    const errorMessage = root.querySelector("[data-audio-error-message]");

    const extensionLabel = root.querySelector("[data-audio-extension]");
    const durationLabel = root.querySelector("[data-audio-duration]");
    const levelLabel = root.querySelector("[data-audio-level]");
    const status = root.querySelector("[data-audio-status]");

    const playButton = root.querySelector("[data-audio-play]");
    const playIcon = root.querySelector("[data-audio-play-icon]");
    const muteButton = root.querySelector("[data-audio-mute]");
    const volumeWave = root.querySelector("[data-audio-volume-wave]");
    const muteCross = root.querySelector("[data-audio-mute-cross]");
    const volumeSlider = root.querySelector("[data-audio-volume]");
    const speedSelect = root.querySelector("[data-audio-speed]");

    const progress = root.querySelector("[data-audio-progress]");
    const currentTimeLabel = root.querySelector("[data-audio-current-time]");
    const totalTimeLabel = root.querySelector("[data-audio-total-time]");

    /* --------------------------------------------------
       Settings
       -------------------------------------------------- */

    const MIN_HALF = 1;         // half-height of the idle line, px (total 2 px)
    const BAR_WIDTH = 5;        // bar width, px
    const BAR_GAP = 7;          // gap between bars, px
    const STEP = BAR_WIDTH + BAR_GAP;
    const SAMPLE_MS = 96;       // one new bar every 96 ms (12 px / 0.096 s = 125 px/s)
    const MIN_DB = -60;
    const FFT_SIZE = 4096;      // analysis window, ~90 ms

    // Animation, measured in bars (1 bar = STEP px). Fractions are fine.
    const GROW_BARS = 2.5;        // how many bars take part in the growth
    const GROW_DELAY_BARS = 0;    // growth starts this many bars LEFT of the "now" line (0 or more)
    const FADE_BARS = 2.5;        // how many bars take part in the fade
    const FADE_SHIFT_BARS = 0;    // fade ends this many bars RIGHT of the left margin (negative = further left)
    const NOW_SHIFT_BARS = 0;     // the "now" line itself moves this many bars LEFT of the right margin

    const GROW_PX = GROW_BARS * STEP;
    const GROW_DELAY = GROW_DELAY_BARS * STEP;
    const FADE_PX = FADE_BARS * STEP;
    const FADE_SHIFT = FADE_SHIFT_BARS * STEP;
    const NOW_SHIFT = NOW_SHIFT_BARS * STEP;

    const ATTACK = 1;           // level jumps up instantly
    const RELEASE = 0.55;       // and falls quickly

    /* --------------------------------------------------
       State
       -------------------------------------------------- */
    let smoothLevel = 0;        // smoothed loudness 0..1
    let gutter = 0;             // side margin in px, read from CSS (--au-gutter)

    let volume = 1;
    let muted = false;

    let history = [];           // loudness values 0..1, oldest first
    let accumulator = 0;        // ms since the last bar was added
    let lastFrame = 0;
    let frameId = 0;
    let barColor = getComputedStyle(canvas).color;

    /* --------------------------------------------------
       Helpers
       -------------------------------------------------- */

    // Ошибка до создания плеера (нет Web Audio)
    function showFatal(message) {
        loading.hidden = true;
        error.hidden = false;
        errorMessage.textContent = message;
        status.textContent = "ERROR";
    }

    function setExtension() {
        const filename = root.dataset.audioFilename || "";
        const dotIndex = filename.lastIndexOf(".");
        const extension = dotIndex >= 0
            ? filename.slice(dotIndex + 1).toUpperCase()
            : "UNKNOWN";

        extensionLabel.textContent = `[AUDIO.${extension}]`;
    }

    function updateMetadata() {
        durationLabel.textContent = Aether.formatTime(audio.duration);
    }

    /* --------------------------------------------------
       Audio graph
       audio element -> analyser -> gain -> speakers
       Volume lives in the gain node AFTER the analyser,
       so the graph keeps moving even when muted.
       -------------------------------------------------- */

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;

    if (!AudioContextClass) {
        showFatal("This browser does not support Web Audio.");
        return;
    }

    const audioContext = new AudioContextClass();
    const sourceNode = audioContext.createMediaElementSource(audio);
    const analyser = audioContext.createAnalyser();
    const gainNode = audioContext.createGain();

    analyser.fftSize = FFT_SIZE;

    sourceNode.connect(analyser);
    analyser.connect(gainNode);
    gainNode.connect(audioContext.destination);

    const samples = new Float32Array(analyser.fftSize);

    // Current loudness in dB (0 = loudest possible, MIN_DB = silence)
    function measureDb() {
        analyser.getFloatTimeDomainData(samples);

        let sum = 0;

        for (let i = 0; i < samples.length; i++) {
            sum += samples[i] * samples[i];
        }

        const rms = Math.sqrt(sum / samples.length);
        const db = rms > 0 ? 20 * Math.log10(rms) : MIN_DB;

        return Math.max(db, MIN_DB);
    }

    /* --------------------------------------------------
       Loudness graph
       -------------------------------------------------- */

    function resizeCanvas() {
        const ratio = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();

        canvas.width = Math.round(rect.width * ratio);
        canvas.height = Math.round(rect.height * ratio);

        // Draw in CSS pixels; the browser scales to device pixels
        context2d.setTransform(ratio, 0, 0, ratio, 0, 0);
        
        gutter = parseFloat(
            getComputedStyle(canvas).getPropertyValue("--au-gutter")
        ) || 0;

        barColor = getComputedStyle(canvas).color;
        draw();
    }

    function addSample() {
        const db = measureDb();

            const target = (db - MIN_DB) / -MIN_DB;
        const rate = target > smoothLevel ? ATTACK : RELEASE;

        smoothLevel += (target - smoothLevel) * rate;
        history.push(smoothLevel);

        levelLabel.textContent = db <= MIN_DB
            ? "-∞ dB"
            : `${db.toFixed(1)} dB`;

        // Keep only the bars that still fit on screen
        const maxBars = Math.ceil(canvas.clientWidth / STEP) + 2;

        while (history.length > maxBars) {
            history.shift();
        }
    }

    // Fast at first, slow at the end (easeOutCubic), t is 0..1
    function ease(t) {
        return 1 - Math.pow(1 - t, 3);
    }

    function draw() {
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;
        const middle = height / 2;
        const maxHalf = height * 0.34;

        // Right boundary of the active zone: the "now" line
        const right = width - gutter - NOW_SHIFT;

        context2d.clearRect(0, 0, width, height);
        context2d.fillStyle = barColor;

        // Part of a step already travelled: makes the motion smooth
        const offset = (accumulator / SAMPLE_MS) * STEP;

        // Start a bit to the right of the canvas so the gutter is filled too
        const first = -Math.ceil((width - right) / STEP) - 1;

        // j = 0 is the newest bar on the "now" line, j < 0 are idle bars to its right
        for (let j = first; ; j++) {
            const x = right - j * STEP - offset;

            if (x > width) {
                continue;
            }

            // Everything further left is already outside the canvas
            if (x + BAR_WIDTH < 0) {
                break;
            }

            const level = history[history.length - 1 - j] || 0;

            const grow = Math.min(1, Math.max(0, (right - x - GROW_DELAY) / GROW_PX));
            const fade = Math.min(1, Math.max(0, (x + BAR_WIDTH - gutter - FADE_SHIFT) / FADE_PX));

            const half = MIN_HALF + level * maxHalf * ease(grow) * ease(fade);

            context2d.fillRect(x, middle - half, BAR_WIDTH, half * 2);
        }
    }

    function tick(now) {
        frameId = requestAnimationFrame(tick);

        // Clamp so a background tab does not dump hundreds of bars at once
        accumulator += Math.min(now - lastFrame, 100);
        lastFrame = now;

        while (accumulator >= SAMPLE_MS) {
            accumulator -= SAMPLE_MS;
            addSample();
        }

        draw();
    }

    function startLoop() {
        if (frameId) {
            return;
        }

        lastFrame = performance.now();
        frameId = requestAnimationFrame(tick);
    }

    function stopLoop() {
        cancelAnimationFrame(frameId);
        frameId = 0;
    }

    function clearGraph() {
        history = [];
        accumulator = 0;
        smoothLevel = 0;
        levelLabel.textContent = "—";
        draw();
    }

    new ResizeObserver(resizeCanvas).observe(canvas);

    /* --------------------------------------------------
       Player
       Громкость живёт в gain-узле ПОСЛЕ анализатора, поэтому
       график идёт и при mute: свою модель громкости отдаём ядру.
       -------------------------------------------------- */

    const player = Aether.createPlayer(
        audio,
        {
            status: status,
            playButton: playButton,
            playIcon: playIcon,
            muteButton: muteButton,
            wave: volumeWave,
            cross: muteCross,
            volume: volumeSlider,
            speed: speedSelect,
            progress: progress,
            current: currentTimeLabel,
            total: totalTimeLabel,
            loading: loading,
            error: error,
            errorMessage: errorMessage,
        },
        {
            label: "audio",
            progressVar: "--au-progress",
            onMetadata: updateMetadata,
            onError: stopLoop,
            // Браузер держит контекст приостановленным до действия пользователя
            beforePlay: function () {
                return audioContext.resume();
            },
            volumeModel: {
                get: function () {
                    return volume;
                },
                isMuted: function () {
                    return muted;
                },
                setVolume: function (value) {
                    volume = value;
                },
                setMuted: function (value) {
                    muted = value;

                    if (!muted && volume === 0) {
                        volume = 1;
                    }
                },
            },
        }
    );

    // Громкость применяется к gain-узлу при каждом изменении интерфейса
    const applyVolume = function () {
        gainNode.gain.value = muted || volume === 0 ? 0 : volume;
    };

    [muteButton, volumeSlider].forEach(function (el) {
        el.addEventListener("click", applyVolume);
        el.addEventListener("input", applyVolume);
    });

    audio.addEventListener("play", startLoop);
    audio.addEventListener("pause", stopLoop);
    audio.addEventListener("ended", stopLoop);
    audio.addEventListener("seeked", clearGraph);

    document.addEventListener("keydown", function (event) {
        if (
            event.defaultPrevented ||
            event.ctrlKey ||
            event.altKey ||
            event.metaKey
        ) {
            return;
        }

        const target = event.target;

        if (
            target instanceof HTMLElement &&
            (
                target.isContentEditable ||
                ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(target.tagName)
            )
        ) {
            return;
        }

        if (player.handleKey(event) && event.key.toLowerCase() === "m") {
            applyVolume();
        }
    });

    setExtension();
    applyVolume();
    resizeCanvas();
})();
