/* ==================================================
   AETHER OS / AUDIO VIEWER
   Playback, custom controls and live loudness graph
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
    let failed = false;
    let seeking = false;

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

    const formatTime = Aether.formatTime;

    function setStatus(value) {
        status.textContent = value;
    }

    function showError(message) {
        failed = true;
        stopLoop();

        loading.hidden = true;
        error.hidden = false;
        errorMessage.textContent = message || "Unable to load audio source.";

        setStatus("ERROR");
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
        durationLabel.textContent = formatTime(audio.duration);
        totalTimeLabel.textContent = formatTime(audio.duration);
    }

    /* --------------------------------------------------
       Audio graph
       audio element -> analyser -> gain -> speakers
       Volume lives in the gain node AFTER the analyser,
       so the graph keeps moving even when muted.
       -------------------------------------------------- */

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;

    if (!AudioContextClass) {
        showError("This browser does not support Web Audio.");
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
       Playback
       -------------------------------------------------- */

    function updatePlayState() {
        const playing = !audio.paused && !audio.ended;

        playButton.setAttribute("aria-label", playing ? "Pause" : "Play");
        playButton.title = playing ? "Pause (Space)" : "Play (Space)";

        playIcon.innerHTML = playing
            ? '<path d="M7 5h4v14H7zM15 5h4v14h-4z" />'
            : '<path d="M8 5.5 19 12 8 18.5Z" />';

        if (failed) {
            setStatus("ERROR");
        } else if (audio.ended) {
            setStatus("END OF FILE");
        } else if (playing) {
            setStatus("PLAYING");
        } else if (audio.currentTime > 0) {
            setStatus("PAUSED");
        } else {
            setStatus("READY");
        }
    }

    async function togglePlayback() {
        if (failed) {
            return;
        }

        if (audio.paused || audio.ended) {
            if (audio.ended) {
                audio.currentTime = 0;
            }

            try {
                // Browsers keep the audio context suspended until a user action
                await audioContext.resume();
                await audio.play();
            } catch (err) {
                showError(
                    "Playback could not be started. The format may not be supported by this browser."
                );
            }
        } else {
            audio.pause();
        }
    }

    playButton.addEventListener("click", togglePlayback);

    audio.addEventListener("play", function () {
        updatePlayState();
        startLoop();
    });

    audio.addEventListener("pause", function () {
        updatePlayState();
        stopLoop();
    });

    audio.addEventListener("ended", function () {
        updatePlayState();
        stopLoop();
    });

    audio.addEventListener("seeked", clearGraph);

    audio.addEventListener("waiting", function () {
        if (!audio.paused) {
            setStatus("BUFFERING");
        }
    });

    audio.addEventListener("playing", updatePlayState);

    /* --------------------------------------------------
       Timeline
       -------------------------------------------------- */

    function updateProgress() {
        const duration = audio.duration;
        const current = audio.currentTime;

        currentTimeLabel.textContent = formatTime(current);

        if (!seeking && Number.isFinite(duration) && duration > 0) {
            const value = Math.round((current / duration) * 1000);

            progress.value = String(value);
            progress.style.setProperty("--au-progress", `${value / 10}%`);
        }
    }

    function seekFromSlider() {
        const duration = audio.duration;

        if (!Number.isFinite(duration) || duration <= 0) {
            return;
        }

        audio.currentTime = (Number(progress.value) / 1000) * duration;
    }

    progress.addEventListener("pointerdown", function () {
        seeking = true;
    });

    progress.addEventListener("input", function () {
        const fraction = Number(progress.value) / 1000;

        progress.style.setProperty("--au-progress", `${fraction * 100}%`);

        if (Number.isFinite(audio.duration)) {
            currentTimeLabel.textContent = formatTime(fraction * audio.duration);
        }
    });

    progress.addEventListener("change", function () {
        seekFromSlider();
        seeking = false;
    });

    audio.addEventListener("timeupdate", updateProgress);
    audio.addEventListener("durationchange", updateMetadata);
    audio.addEventListener("loadedmetadata", updateMetadata);

    /* --------------------------------------------------
       Volume and mute
       -------------------------------------------------- */

    function updateVolumeUI() {
        const silent = muted || volume === 0;

        gainNode.gain.value = silent ? 0 : volume;
        volumeSlider.value = String(silent ? 0 : volume);

        muteButton.setAttribute("aria-label", silent ? "Unmute" : "Mute");

        volumeWave.hidden = silent;
        muteCross.hidden = !silent;
    }

    muteButton.addEventListener("click", function () {
        muted = !muted;

        if (!muted && volume === 0) {
            volume = 1;
        }

        updateVolumeUI();
    });

    volumeSlider.addEventListener("input", function () {
        volume = Number(volumeSlider.value);
        muted = volume === 0;

        updateVolumeUI();
    });

    /* --------------------------------------------------
       Playback speed
       -------------------------------------------------- */

    speedSelect.addEventListener("change", function () {
        audio.playbackRate = Number(speedSelect.value);
    });

    /* --------------------------------------------------
       Keyboard shortcuts
       -------------------------------------------------- */

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

        switch (event.key.toLowerCase()) {
            case " ":
                event.preventDefault();
                togglePlayback();
                break;

            case "arrowleft":
                event.preventDefault();
                audio.currentTime = Math.max(0, audio.currentTime - 5);
                break;

            case "arrowright":
                event.preventDefault();
                audio.currentTime = Number.isFinite(audio.duration)
                    ? Math.min(audio.duration, audio.currentTime + 5)
                    : audio.currentTime + 5;
                break;

            case "m":
                muted = !muted;
                updateVolumeUI();
                break;
        }
    });

    /* --------------------------------------------------
       Loading and errors
       -------------------------------------------------- */

    audio.addEventListener("loadedmetadata", function () {
        loading.hidden = true;
        updateMetadata();
        updateProgress();
        updatePlayState();
    });

    audio.addEventListener("error", function () {
        let message = "Unable to load audio source.";

        if (audio.error) {
            switch (audio.error.code) {
                case MediaError.MEDIA_ERR_ABORTED:
                    message = "Audio loading was aborted.";
                    break;

                case MediaError.MEDIA_ERR_NETWORK:
                    message = "A network error interrupted audio loading.";
                    break;

                case MediaError.MEDIA_ERR_DECODE:
                    message = "The audio could not be decoded.";
                    break;

                case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
                    message = "This audio format or codec is not supported.";
                    break;
            }
        }

        showError(message);
    });

    /* --------------------------------------------------
       Initial state
       -------------------------------------------------- */

    setExtension();
    updateVolumeUI();
    updatePlayState();
    resizeCanvas();

    if (audio.readyState >= HTMLMediaElement.HAVE_METADATA) {
        loading.hidden = true;
        updateMetadata();
        updateProgress();
    } else if (audio.error) {
        showError("Unable to load audio source.");
    }
})();