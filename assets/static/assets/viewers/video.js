
/* ==================================================
   AETHER OS / VIDEO VIEWER
   Playback, custom controls and auto-hide
   ================================================== */

(function () {
    "use strict";

    const root = document.querySelector("[data-video-viewer]");

    if (!root) {
        return;
    }

    const stage = root.querySelector("[data-video-stage]");
    const video = root.querySelector("[data-video-source]");

    const loading = root.querySelector("[data-video-loading]");
    const error = root.querySelector("[data-video-error]");
    const errorMessage = root.querySelector("[data-video-error-message]");

    const metadata = root.querySelector(".vv-metadata");
    const controls = root.querySelector("[data-video-controls]");
    const centerPlay = root.querySelector("[data-video-center-play]");

    const extensionLabel = root.querySelector("[data-video-extension]");
    const resolution = root.querySelector("[data-video-resolution]");
    const durationLabel = root.querySelector("[data-video-duration]");
    const status = root.querySelector("[data-video-status]");

    const playButton = root.querySelector("[data-video-play]");
    const playIcon = root.querySelector("[data-video-play-icon]");
    const muteButton = root.querySelector("[data-video-mute]");
    const volumeWave = root.querySelector("[data-video-volume-wave]");
    const muteCross = root.querySelector("[data-video-mute-cross]");
    const volumeSlider = root.querySelector("[data-video-volume]");
    const speedSelect = root.querySelector("[data-video-speed]");
    const fullscreenButton = root.querySelector("[data-video-fullscreen]");

    const progress = root.querySelector("[data-video-progress]");
    const currentTimeLabel = root.querySelector("[data-video-current-time]");
    const totalTimeLabel = root.querySelector("[data-video-total-time]");

    const AUTO_HIDE_DELAY = 2200;

    let hideTimer = null;
    let seeking = false;
    let failed = false;

    /* --------------------------------------------------
       Metadata
       -------------------------------------------------- */

    function setExtension() {
        const filename = root.dataset.videoFilename || "";
        const dotIndex = filename.lastIndexOf(".");
        const extension = dotIndex >= 0
            ? filename.slice(dotIndex + 1).toUpperCase()
            : "UNKNOWN";

        extensionLabel.textContent = `[VIDEO.${extension}]`;
    }

    
    const formatTime = Aether.formatTime;

    function updateMetadata() {
        if (video.videoWidth && video.videoHeight) {
            resolution.textContent =
                `${video.videoWidth} × ${video.videoHeight}`;
        }

        durationLabel.textContent = formatTime(video.duration);
        totalTimeLabel.textContent = formatTime(video.duration);
    }

    /* --------------------------------------------------
       Status and errors
       -------------------------------------------------- */

    function setStatus(value) {
        status.textContent = value;
    }

    function showError(message) {
        failed = true;

        clearTimeout(hideTimer);
        showControls();

        loading.hidden = true;
        error.hidden = false;
        errorMessage.textContent =
            message || "Unable to load video source.";

        centerPlay.hidden = true;
        setStatus("ERROR");
    }

    function hideLoading() {
        loading.hidden = true;
    }

    /* --------------------------------------------------
       Playback
       -------------------------------------------------- */

    function updatePlayState() {
        const playing = !video.paused && !video.ended;

        stage.classList.toggle("vv-is-playing", playing);

        playButton.setAttribute(
            "aria-label",
            playing ? "Pause" : "Play"
        );

        playButton.title = playing
            ? "Pause (Space)"
            : "Play (Space)";

        playIcon.innerHTML = playing
            ? '<path d="M7 5h4v14H7zM15 5h4v14h-4z" />'
            : '<path d="M8 5.5 19 12 8 18.5Z" />';

        centerPlay.hidden = playing || failed;

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
                showError(
                    "Playback could not be started. The format may not be supported by this browser."
                );
            }
        } else {
            video.pause();
        }

        showControls();
    }

    playButton.addEventListener("click", function (event) {
        event.stopPropagation();
        togglePlayback();
    });

    centerPlay.addEventListener("click", function (event) {
        event.stopPropagation();
        togglePlayback();
    });

    video.addEventListener("click", function () {
        togglePlayback();
    });

    video.addEventListener("play", function () {
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

    /* --------------------------------------------------
       Timeline
       -------------------------------------------------- */

    function updateProgress() {
        const duration = video.duration;
        const current = video.currentTime;

        currentTimeLabel.textContent = formatTime(current);

        if (!seeking && Number.isFinite(duration) && duration > 0) {
            const value = Math.round((current / duration) * 1000);

            progress.value = String(value);
            progress.style.setProperty(
                "--vv-progress",
                `${(value / 1000) * 100}%`
            );
        }
    }

    function seekFromSlider() {
        const duration = video.duration;

        if (!Number.isFinite(duration) || duration <= 0) {
            return;
        }

        const fraction = Number(progress.value) / 1000;
        video.currentTime = fraction * duration;

        progress.style.setProperty(
            "--vv-progress",
            `${fraction * 100}%`
        );

        currentTimeLabel.textContent = formatTime(video.currentTime);
    }

    progress.addEventListener("pointerdown", function () {
        seeking = true;
        showControls();
    });

    progress.addEventListener("input", function () {
        const fraction = Number(progress.value) / 1000;
        const duration = video.duration;

        progress.style.setProperty(
            "--vv-progress",
            `${fraction * 100}%`
        );

        if (Number.isFinite(duration) && duration > 0) {
            currentTimeLabel.textContent = formatTime(fraction * duration);
        }
    });

    progress.addEventListener("change", function () {
        seekFromSlider();
        seeking = false;
        scheduleHide();
    });

    progress.addEventListener("pointerup", function () {
        if (seeking) {
            seekFromSlider();
            seeking = false;
            scheduleHide();
        }
    });

    video.addEventListener("timeupdate", updateProgress);
    video.addEventListener("durationchange", updateMetadata);
    video.addEventListener("loadedmetadata", updateMetadata);

    /* --------------------------------------------------
       Volume and mute
       -------------------------------------------------- */

    function updateVolumeUI() {
        volumeSlider.value = String(video.muted ? 0 : video.volume);

        muteButton.setAttribute(
            "aria-label",
            video.muted || video.volume === 0
                ? "Unmute"
                : "Mute"
        );

        volumeWave.hidden = video.muted || video.volume === 0;
        muteCross.hidden = !video.muted && video.volume > 0;
    }

    muteButton.addEventListener("click", function (event) {
        event.stopPropagation();

        video.muted = !video.muted;
        updateVolumeUI();
        showControls();
    });

    volumeSlider.addEventListener("input", function () {
        video.volume = Number(volumeSlider.value);
        video.muted = video.volume === 0;

        updateVolumeUI();
        showControls();
    });

    video.addEventListener("volumechange", updateVolumeUI);

    /* --------------------------------------------------
       Playback speed
       -------------------------------------------------- */

    speedSelect.addEventListener("change", function () {
        video.playbackRate = Number(speedSelect.value);
        showControls();
    });

    /* --------------------------------------------------
       Fullscreen
       -------------------------------------------------- */

    function isFullscreen() {
        return document.fullscreenElement === root ||
            document.fullscreenElement === stage;
    }

    async function toggleFullscreen() {
        await Aether.toggleFullscreen(root, video);

        updateFullscreenButton();
        showControls();
    }

    function updateFullscreenButton() {
        const active = isFullscreen();

        fullscreenButton.setAttribute(
            "aria-label",
            active ? "Exit fullscreen" : "Enter fullscreen"
        );

        fullscreenButton.title = active
            ? "Exit fullscreen (F)"
            : "Fullscreen (F)";
    }

    fullscreenButton.addEventListener("click", function (event) {
        event.stopPropagation();
        toggleFullscreen();
    });

    document.addEventListener("fullscreenchange", updateFullscreenButton);

    /* --------------------------------------------------
       Auto-hide controls
       -------------------------------------------------- */

    function showControls() {
        clearTimeout(hideTimer);
        stage.classList.remove("vv-controls-hidden");
    }

    function scheduleHide() {
        clearTimeout(hideTimer);

        if (
            video.paused ||
            video.ended ||
            failed ||
            seeking
        ) {
            showControls();
            return;
        }

        hideTimer = setTimeout(function () {
            if (
                !controls.matches(":hover") &&
                !metadata.matches(":hover")
            ) {
                stage.classList.add("vv-controls-hidden");
            }
        }, AUTO_HIDE_DELAY);
    }

    stage.addEventListener("pointermove", function () {
        showControls();

        if (!video.paused) {
            scheduleHide();
        }
    });

    stage.addEventListener("pointerleave", function () {
        if (!video.paused) {
            scheduleHide();
        }
    });

    controls.addEventListener("pointerenter", showControls);
    controls.addEventListener("pointermove", showControls);

    controls.addEventListener("pointerleave", function () {
        if (!video.paused) {
            scheduleHide();
        }
    });

    metadata.addEventListener("pointerenter", showControls);

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

        if (!root.isConnected) {
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
                showControls();
                break;

            case "arrowright":
                event.preventDefault();

                video.currentTime = Number.isFinite(video.duration)
                    ? Math.min(video.duration, video.currentTime + 5)
                    : video.currentTime + 5;

                showControls();
                break;

            case "m":
                video.muted = !video.muted;
                updateVolumeUI();
                showControls();
                break;

            case "f":
                toggleFullscreen();
                break;

            default:
                return;
        }

        if (!video.paused) {
            scheduleHide();
        }
    });

    /* --------------------------------------------------
       Loading
       -------------------------------------------------- */

    setExtension();

    video.addEventListener("loadedmetadata", function () {
        hideLoading();
        updateMetadata();
        updateProgress();
        updatePlayState();
    });

    video.addEventListener("canplay", function () {
        hideLoading();
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

    video.addEventListener("waiting", function () {
        if (!video.paused) {
            setStatus("BUFFERING");
        }
    });

    video.addEventListener("playing", function () {
        updatePlayState();
        scheduleHide();
    });

    /* --------------------------------------------------
       Initial state
       -------------------------------------------------- */

    updateVolumeUI();
    updateFullscreenButton();
    updatePlayState();

    if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
        hideLoading();
        updateMetadata();
        updateProgress();
    } else if (video.error) {
        showError("Unable to load video source.");
    }
})();