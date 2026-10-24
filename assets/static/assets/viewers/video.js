/* ==================================================
   AETHER OS / VIDEO VIEWER
   Подключает общее ядро плеера (static/ui/player-core.js)
   к разметке вьювера.
   ================================================== */

(function () {
    "use strict";

    const root = document.querySelector("[data-video-viewer]");

    if (!root) {
        return;
    }

    const stage = root.querySelector("[data-video-stage]");
    const video = root.querySelector("[data-video-source]");

    const extensionLabel = root.querySelector("[data-video-extension]");
    const resolution = root.querySelector("[data-video-resolution]");
    const durationLabel = root.querySelector("[data-video-duration]");

    function setExtension() {
        const filename = root.dataset.videoFilename || "";
        const dotIndex = filename.lastIndexOf(".");
        const extension = dotIndex >= 0
            ? filename.slice(dotIndex + 1).toUpperCase()
            : "UNKNOWN";

        extensionLabel.textContent = `[VIDEO.${extension}]`;
    }

    function updateMetadata() {
        if (video.videoWidth && video.videoHeight) {
            resolution.textContent = `${video.videoWidth} × ${video.videoHeight}`;
        }

        durationLabel.textContent = Aether.formatTime(video.duration);
    }

    setExtension();

    const player = Aether.createPlayer(
        video,
        {
            stage: stage,
            controls: root.querySelector("[data-video-controls]"),
            status: root.querySelector("[data-video-status]"),
            center: root.querySelector("[data-video-center-play]"),
            playButton: root.querySelector("[data-video-play]"),
            playIcon: root.querySelector("[data-video-play-icon]"),
            muteButton: root.querySelector("[data-video-mute]"),
            wave: root.querySelector("[data-video-volume-wave]"),
            cross: root.querySelector("[data-video-mute-cross]"),
            volume: root.querySelector("[data-video-volume]"),
            speed: root.querySelector("[data-video-speed]"),
            fullscreenButton: root.querySelector("[data-video-fullscreen]"),
            progress: root.querySelector("[data-video-progress]"),
            current: root.querySelector("[data-video-current-time]"),
            total: root.querySelector("[data-video-total-time]"),
            loading: root.querySelector("[data-video-loading]"),
            error: root.querySelector("[data-video-error]"),
            errorMessage: root.querySelector("[data-video-error-message]"),
        },
        {
            label: "video",
            classes: { playing: "vv-is-playing", hidden: "vv-controls-hidden" },
            progressVar: "--vv-progress",
            fullscreenTarget: root,
            hoverGuards: [root.querySelector(".vv-metadata")],
            onMetadata: updateMetadata,
        }
    );

    document.addEventListener("keydown", function (event) {
        if (
            event.defaultPrevented ||
            event.ctrlKey ||
            event.altKey ||
            event.metaKey ||
            !root.isConnected
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

        player.handleKey(event);
    });
})();
