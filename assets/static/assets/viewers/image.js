
/* ==================================================
   AETHER OS / IMAGE VIEWER
   Image navigation and minimap
   ================================================== */

(function () {
    "use strict";

    const root = document.querySelector("[data-image-viewer]");

    if (!root) {
        return;
    }

    const stage = root.querySelector("[data-image-stage]");
    const image = root.querySelector("[data-image-source]");
    const minimap = root.querySelector("[data-image-minimap]");
    const minimapImage = root.querySelector(
        "[data-image-minimap-image]"
    );
    const viewport = root.querySelector(
        "[data-image-minimap-viewport]"
    );

    const loading = root.querySelector("[data-image-loading]");
    const error = root.querySelector("[data-image-error]");
    const resolution = root.querySelector("[data-image-resolution]");
    const zoomLabel = root.querySelector("[data-image-zoom-label]");
    const zoomValue = root.querySelector("[data-image-zoom-value]");
    const viewValue = root.querySelector("[data-image-view-value]");
    const extensionLabel = root.querySelector("[data-image-extension]");

    const state = {
        naturalWidth: 0,
        naturalHeight: 0,

        stageWidth: 0,
        stageHeight: 0,

        baseScale: 1,
        zoom: 1,

        panX: 0,
        panY: 0,

        displayWidth: 0,
        displayHeight: 0,

        left: 0,
        top: 0,

        draggingImage: false,
        draggingMap: false,

        pointerX: 0,
        pointerY: 0,

        dragStartX: 0,
        dragStartY: 0,

        dragPanX: 0,
        dragPanY: 0,

        loaded: false,
    };

    const MIN_ZOOM = 1;
    const MAX_ZOOM = 12;
    const ZOOM_FACTOR = 1.15;

    let resizeObserver = null;

    /* --------------------------------------------------
       Image loading
       -------------------------------------------------- */

    function initializeImage() {
        if (!image.naturalWidth || !image.naturalHeight) {
            showError();
            return;
        }

        const filename = root.dataset.imageFilename || "";
        const dotIndex = filename.lastIndexOf(".");
        const extension = dotIndex >= 0 ? filename.slice(dotIndex + 1).toUpperCase(): "UNKNOWN";

        extensionLabel.textContent = `[IMG.${extension}]`;

        state.naturalWidth = image.naturalWidth;
        state.naturalHeight = image.naturalHeight;
        state.loaded = true;

        const maxWidth = window.innerWidth <= 600 ? 104 : 138;
        const maxHeight = window.innerWidth <= 600 ? 145 : 190;

        const width = state.naturalWidth;
        const height = state.naturalHeight;

        const scale = Math.min(
            maxWidth / width,
            maxHeight / height
        );

        minimap.style.width = `${Math.round(width * scale)}px`;
        minimap.style.height = `${Math.round(height * scale)}px`;

        resolution.textContent = `${state.naturalWidth} × ${state.naturalHeight}`;

        image.classList.add("iv-image-ready");

        loading.hidden = true;
        error.hidden = true;

        resetView();
        observeStage();
    }

    function showError() {
        loading.hidden = true;
        error.hidden = false;
        image.classList.remove("iv-image-ready");
    }

    image.addEventListener("load", initializeImage);
    image.addEventListener("error", showError);

    if (image.complete) {
        if (image.naturalWidth > 0) {
            initializeImage();
        } else {
            showError();
        }
    }

    /* --------------------------------------------------
       Layout and scaling
       -------------------------------------------------- */

    function measureStage() {
        const rect = stage.getBoundingClientRect();

        state.stageWidth = rect.width;
        state.stageHeight = rect.height;
    }

    function calculateBaseScale() {
        if (
            !state.naturalWidth ||
            !state.naturalHeight ||
            !state.stageWidth ||
            !state.stageHeight
        ) {
            return 1;
        }

        return Math.min(
            state.stageWidth / state.naturalWidth,
            state.stageHeight / state.naturalHeight
        );
    }

    function calculateImageGeometry() {
        const scale = state.baseScale * state.zoom;

        state.displayWidth = state.naturalWidth * scale;
        state.displayHeight = state.naturalHeight * scale;

        state.left =
            (state.stageWidth - state.displayWidth) / 2 +
            state.panX;

        state.top =
            (state.stageHeight - state.displayHeight) / 2 +
            state.panY;
    }

    function clampPan() {
        const maxPanX = Math.max(
            0,
            (state.displayWidth - state.stageWidth) / 2
        );

        const maxPanY = Math.max(
            0,
            (state.displayHeight - state.stageHeight) / 2
        );

        state.panX = clamp(
            state.panX,
            -maxPanX,
            maxPanX
        );

        state.panY = clamp(
            state.panY,
            -maxPanY,
            maxPanY
        );
    }

    function renderImage() {
        if (!state.loaded) {
            return;
        }

        measureStage();

        state.baseScale = calculateBaseScale();

        clampPan();
        calculateImageGeometry();

        image.style.width = `${state.displayWidth}px`;
        image.style.height = `${state.displayHeight}px`;

        image.style.left = `${state.left}px`;
        image.style.top = `${state.top}px`;

        image.style.transform = "none";

        updateZoomReadout();
        updateMinimap();
    }

    function resetView() {
        state.zoom = 1;
        state.panX = 0;
        state.panY = 0;

        renderImage();
    }

    /* --------------------------------------------------
       Zoom
       -------------------------------------------------- */

    function zoomAt(nextZoom, pointerX, pointerY) {
        if (!state.loaded) {
            return;
        }

        const newZoom = clamp(
            nextZoom,
            MIN_ZOOM,
            MAX_ZOOM
        );

        if (Math.abs(newZoom - state.zoom) < 0.0001) {
            return;
        }

        const imageX =
            (pointerX - state.left) / state.displayWidth;

        const imageY =
            (pointerY - state.top) / state.displayHeight;

        state.zoom = newZoom;

        measureStage();
        state.baseScale = calculateBaseScale();

        const newWidth =
            state.naturalWidth *
            state.baseScale *
            state.zoom;

        const newHeight =
            state.naturalHeight *
            state.baseScale *
            state.zoom;

        const newLeft = pointerX - imageX * newWidth;
        const newTop = pointerY - imageY * newHeight;

        state.panX =
            newLeft - (state.stageWidth - newWidth) / 2;

        state.panY =
            newTop - (state.stageHeight - newHeight) / 2;

        renderImage();
    }

    stage.addEventListener(
        "wheel",
        function (event) {
            if (!state.loaded) {
                return;
            }

            event.preventDefault();

            const rect = stage.getBoundingClientRect();

            const pointerX = event.clientX - rect.left;
            const pointerY = event.clientY - rect.top;

            const direction = event.deltaY < 0 ? 1 : -1;

            const nextZoom = direction > 0
                ? state.zoom * ZOOM_FACTOR
                : state.zoom / ZOOM_FACTOR;

            zoomAt(nextZoom, pointerX, pointerY);
        },
        { passive: false }
    );

    /* --------------------------------------------------
       Drag the main image
       -------------------------------------------------- */

    stage.addEventListener("pointerdown", function (event) {
        if (!state.loaded || event.button !== 0) {
            return;
        }

        state.draggingImage = true;

        state.pointerX = event.clientX;
        state.pointerY = event.clientY;

        state.dragStartX = event.clientX;
        state.dragStartY = event.clientY;

        state.dragPanX = state.panX;
        state.dragPanY = state.panY;

        stage.classList.add("iv-is-dragging");

        stage.setPointerCapture(event.pointerId);
    });

    stage.addEventListener("pointermove", function (event) {
        if (!state.draggingImage) {
            return;
        }

        state.panX =
            state.dragPanX +
            event.clientX -
            state.dragStartX;

        state.panY =
            state.dragPanY +
            event.clientY -
            state.dragStartY;

        renderImage();
    });

    function stopImageDrag() {
        state.draggingImage = false;
        stage.classList.remove("iv-is-dragging");
    }

    stage.addEventListener("pointerup", stopImageDrag);
    stage.addEventListener("pointercancel", stopImageDrag);
    stage.addEventListener("lostpointercapture", stopImageDrag);

    /* --------------------------------------------------
       Minimap geometry
       -------------------------------------------------- */

    function getMinimapGeometry() {
        const width = minimap.clientWidth;
        const height = minimap.clientHeight;

        if (
            !width ||
            !height ||
            !state.naturalWidth ||
            !state.naturalHeight
        ) {
            return null;
        }

        const scale = Math.min(
            width / state.naturalWidth,
            height / state.naturalHeight
        );

        const imageWidth = state.naturalWidth * scale;
        const imageHeight = state.naturalHeight * scale;

        return {
            width,
            height,
            imageWidth,
            imageHeight,
            left: (width - imageWidth) / 2,
            top: (height - imageHeight) / 2,
        };
    }

    function updateMinimap() {
        if (!state.loaded) {
            return;
        }

        const map = getMinimapGeometry();

        if (!map) {
            return;
        }

        minimapImage.style.width = `${map.imageWidth}px`;
        minimapImage.style.height = `${map.imageHeight}px`;

        minimapImage.style.left = `${map.left}px`;
        minimapImage.style.top = `${map.top}px`;

        /*
         * Find the portion of the source image currently
         * visible inside the main viewport.
         */

        const imageX1 = clamp(
            -state.left / state.displayWidth,
            0,
            1
        );

        const imageY1 = clamp(
            -state.top / state.displayHeight,
            0,
            1
        );

        const imageX2 = clamp(
            (state.stageWidth - state.left) /
                state.displayWidth,
            0,
            1
        );

        const imageY2 = clamp(
            (state.stageHeight - state.top) /
                state.displayHeight,
            0,
            1
        );

        viewport.style.left =
            `${map.left + imageX1 * map.imageWidth}px`;

        viewport.style.top =
            `${map.top + imageY1 * map.imageHeight}px`;

        viewport.style.width =
            `${Math.max(2, (imageX2 - imageX1) * map.imageWidth)}px`;

        viewport.style.height =
            `${Math.max(2, (imageY2 - imageY1) * map.imageHeight)}px`;

        const fullFrame =
            state.zoom <= 1.001 &&
            Math.abs(state.panX) < 1 &&
            Math.abs(state.panY) < 1;

        viewValue.textContent = fullFrame
            ? "FULL FRAME"
            : "REGION";
    }

    /* --------------------------------------------------
       Navigate by clicking or dragging the minimap
       -------------------------------------------------- */

    function navigateFromMinimap(event) {
        if (!state.loaded) {
            return;
        }

        const map = getMinimapGeometry();

        if (!map) {
            return;
        }

        const rect = minimap.getBoundingClientRect();

        const x = clamp(
            event.clientX - rect.left - map.left,
            0,
            map.imageWidth
        );

        const y = clamp(
            event.clientY - rect.top - map.top,
            0,
            map.imageHeight
        );

        const imageX = x / map.imageWidth;
        const imageY = y / map.imageHeight;

        const targetX =
            imageX * state.displayWidth;

        const targetY =
            imageY * state.displayHeight;

        state.panX =
            state.stageWidth / 2 -
            targetX -
            (state.stageWidth - state.displayWidth) / 2;

        state.panY =
            state.stageHeight / 2 -
            targetY -
            (state.stageHeight - state.displayHeight) / 2;

        renderImage();
    }

    minimap.addEventListener("pointerdown", function (event) {
        if (event.button !== 0 || !state.loaded) {
            return;
        }

        event.preventDefault();

        state.draggingMap = true;

        minimap.setPointerCapture(event.pointerId);

        navigateFromMinimap(event);
    });

    minimap.addEventListener("pointermove", function (event) {
        if (!state.draggingMap) {
            return;
        }

        navigateFromMinimap(event);
    });

    function stopMapDrag() {
        state.draggingMap = false;
    }

    minimap.addEventListener("pointerup", stopMapDrag);
    minimap.addEventListener("pointercancel", stopMapDrag);
    minimap.addEventListener("lostpointercapture", stopMapDrag);

    /* --------------------------------------------------
       Readouts
       -------------------------------------------------- */

    function updateZoomReadout() {
        const percent = Math.round(state.zoom * 100);

        zoomLabel.textContent = `${percent}%`;
        zoomValue.textContent = `${percent}%`;
    }

    /* --------------------------------------------------
       Resize handling
       -------------------------------------------------- */

    function observeStage() {
        if (!("ResizeObserver" in window)) {
            window.addEventListener("resize", renderImage);
            return;
        }

        if (resizeObserver) {
            resizeObserver.disconnect();
        }

        resizeObserver = new ResizeObserver(function () {
            renderImage();
        });

        resizeObserver.observe(stage);
        resizeObserver.observe(minimap);
    }

    /* --------------------------------------------------
       Utilities
       -------------------------------------------------- */

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }
})();
