
/* ==================================================
   AETHER OS — PDF VIEWER
   ================================================== */

(function () {
    "use strict";

    const root = document.querySelector("[data-pdf-viewer]");

    if (!root) {
        return;
    }

    const $ = (selector) => root.querySelector(selector);

    const elements = {
        viewport: $("[data-pdf-viewport]"),
        pageArea: $("[data-pdf-page-area]"),
        pageFrame: $("[data-pdf-page-frame]"),
        canvas: $("[data-pdf-canvas]"),

        loading: $("[data-pdf-loading]"),
        loadingMessage: $("[data-pdf-loading-message]"),
        error: $("[data-pdf-error]"),
        errorMessage: $("[data-pdf-error-message]"),

        status: $("[data-pdf-status]"),
        pageCount: $("[data-pdf-page-count]"),
        pageTotal: $("[data-pdf-page-total]"),
        pageInput: $("[data-pdf-page-input]"),
        zoomValue: $("[data-pdf-zoom-value]"),
        renderStatus: $("[data-pdf-render-status]"),
        dimensions: $("[data-pdf-dimensions]"),

        previous: $("[data-pdf-prev]"),
        next: $("[data-pdf-next]"),
        zoomOut: $("[data-pdf-zoom-out]"),
        zoomIn: $("[data-pdf-zoom-in]"),
        fit: $("[data-pdf-fit]"),
        fullscreen: $("[data-pdf-fullscreen]"),
    };

    const MIN_ZOOM = 0.25;
    const MAX_ZOOM = 3;
    const ZOOM_STEP = 0.25;
    const PAGE_PADDING = 52;

    let pdfDocument = null;
    let currentPage = 1;
    let zoom = 1;
    let fitWidth = false;
    let renderTask = null;
    let renderSequence = 0;
    let resizeFrame = 0;

    const disabledControls = [
        elements.pageInput,
        elements.previous,
        elements.next,
        elements.zoomOut,
        elements.zoomIn,
        elements.fit,
        elements.fullscreen,
    ].filter(Boolean);

    function setControlsEnabled(enabled) {
        disabledControls.forEach((element) => {
            element.disabled = !enabled;
        });
    }

    function setStatus(value) {
        if (elements.status) {
            elements.status.textContent = value;
        }
    }

    function setLoadingMessage(value) {
        if (elements.loadingMessage) {
            elements.loadingMessage.textContent = value;
        }
    }

    function setRenderStatus(value) {
        if (elements.renderStatus) {
            elements.renderStatus.textContent = value;
        }
    }

    function showLoading(message) {
        setLoadingMessage(message);

        if (elements.loading) {
            elements.loading.hidden = false;
        }

        if (elements.error) {
            elements.error.hidden = true;
        }

        if (elements.pageArea) {
            elements.pageArea.hidden = true;
        }
    }

    function showError(message) {
        if (elements.loading) {
            elements.loading.hidden = true;
        }

        if (elements.pageArea) {
            elements.pageArea.hidden = true;
        }

        if (elements.error) {
            elements.error.hidden = false;
        }

        if (elements.errorMessage) {
            elements.errorMessage.textContent = message;
        }

        setStatus("ERROR");
        setRenderStatus("RENDERER / FAILED");
    }

    function formatZoom(value) {
        return `${Math.round(value * 100)}%`;
    }

    function updateZoomReadout(actualScale = null) {
        if (elements.zoomValue) {
            elements.zoomValue.textContent = formatZoom(
                actualScale !== null ? actualScale : zoom
            );
        }

        if (elements.zoomOut) {
            elements.zoomOut.disabled = !pdfDocument || zoom <= MIN_ZOOM;
        }

        if (elements.zoomIn) {
            elements.zoomIn.disabled = !pdfDocument || zoom >= MAX_ZOOM;
        }
    }

    function updatePageControls() {
        if (!pdfDocument) {
            return;
        }

        if (elements.pageInput) {
            elements.pageInput.value = String(currentPage);
            elements.pageInput.max = String(pdfDocument.numPages);
        }

        if (elements.pageTotal) {
            elements.pageTotal.textContent = String(pdfDocument.numPages);
        }

        if (elements.previous) {
            elements.previous.disabled = currentPage <= 1;
        }

        if (elements.next) {
            elements.next.disabled = currentPage >= pdfDocument.numPages;
        }

        updateZoomReadout();
    }

    function getPageScale(page) {
        if (!fitWidth) {
            return zoom;
        }

        const baseViewport = page.getViewport({ scale: 1 });

        const availableWidth = Math.max(
            100,
            elements.viewport.clientWidth - PAGE_PADDING
        );

        return Math.min(
            MAX_ZOOM,
            Math.max(MIN_ZOOM, availableWidth / baseViewport.width)
        );
    }

    async function renderPage() {
        if (!pdfDocument || !elements.canvas || !elements.viewport) {
            return;
        }

        const sequence = ++renderSequence;

        if (renderTask) {
            try {
                renderTask.cancel();
            } catch (_) {
                // Previous render may already have completed.
            }

            renderTask = null;
        }

        if (elements.loading) {
            elements.loading.hidden = false;
        }

        if (elements.error) {
            elements.error.hidden = true;
        }

        if (elements.pageArea) {
            elements.pageArea.hidden = true;
        }

        setLoadingMessage(
            `RENDERING PAGE ${String(currentPage).padStart(2, "0")}`
        );
        setStatus("RENDERING");
        setRenderStatus("RENDERER / RENDERING");

        try {
            const page = await pdfDocument.getPage(currentPage);

            if (sequence !== renderSequence) {
                return;
            }

            const scale = getPageScale(page);
            const viewport = page.getViewport({ scale });

            const outputScale = Math.min(
                window.devicePixelRatio || 1,
                2
            );

            const canvas = elements.canvas;
            const context = canvas.getContext("2d", {
                alpha: false,
            });

            if (!context) {
                throw new Error("Unable to initialize the PDF canvas.");
            }

            canvas.width = Math.max(
                1,
                Math.floor(viewport.width * outputScale)
            );

            canvas.height = Math.max(
                1,
                Math.floor(viewport.height * outputScale)
            );

            canvas.style.width = `${viewport.width}px`;
            canvas.style.height = `${viewport.height}px`;

            if (elements.pageFrame) {
                elements.pageFrame.style.width = `${viewport.width}px`;
                elements.pageFrame.style.height = `${viewport.height}px`;
            }

            if (elements.dimensions) {
                elements.dimensions.textContent =
                    `${Math.round(viewport.width)} × ${Math.round(viewport.height)} PX`;
            }

            const task = page.render({
                canvasContext: context,
                viewport,
                transform: outputScale !== 1
                    ? [outputScale, 0, 0, outputScale, 0, 0]
                    : null,
                background: "#ffffff",
            });

            renderTask = task;
            await task.promise;

            if (sequence !== renderSequence) {
                return;
            }

            renderTask = null;

            if (elements.loading) {
                elements.loading.hidden = true;
            }

            if (elements.error) {
                elements.error.hidden = true;
            }

            if (elements.pageArea) {
                elements.pageArea.hidden = false;
                elements.pageArea.style.minWidth = "100%";
            }

            updatePageControls();
            updateZoomReadout(scale);

            setStatus("READY");
            setRenderStatus("RENDERER / PDF.JS");
        } catch (error) {
            if (error && error.name === "RenderingCancelledException") {
                return;
            }

            if (sequence !== renderSequence) {
                return;
            }

            renderTask = null;
            console.error("Aether PDF render error:", error);

            showError("Unable to render this PDF page.");
        }
    }

    async function goToPage(pageNumber) {
        if (!pdfDocument) {
            return;
        }

        const page = Math.max(
            1,
            Math.min(
                pdfDocument.numPages,
                Math.trunc(Number(pageNumber)) || 1
            )
        );

        currentPage = page;
        updatePageControls();

        elements.viewport.scrollTop = 0;
        elements.viewport.scrollLeft = 0;

        await renderPage();
    }

    function changeZoom(amount) {
        if (!pdfDocument) {
            return;
        }

        fitWidth = false;

        zoom = Math.min(
            MAX_ZOOM,
            Math.max(
                MIN_ZOOM,
                Math.round((zoom + amount) * 100) / 100
            )
        );

        updateZoomReadout();
        renderPage();
    }

    function fitPageToWidth() {
        if (!pdfDocument) {
            return;
        }

        fitWidth = true;
        renderPage();
    }

    async function toggleFullscreen() {
        try {
            if (!document.fullscreenElement) {
                await root.requestFullscreen();
            } else {
                await document.exitFullscreen();
            }
        } catch (error) {
            console.error("Aether PDF fullscreen error:", error);
        }
    }

    function updateFullscreenLabel() {
        if (!elements.fullscreen) {
            return;
        }

        const active = document.fullscreenElement === root;

        elements.fullscreen.textContent = active
            ? "EXIT FULLSCREEN"
            : "FULLSCREEN";

        elements.fullscreen.setAttribute(
            "aria-label",
            active ? "Exit fullscreen" : "Enter fullscreen"
        );
    }

    async function initialize() {
        setControlsEnabled(false);
        showLoading("INITIALIZING PDF ENGINE");

        if (!window.pdfjsLib) {
            showError("PDF.js could not be loaded. Check the CDN connection.");
            return;
        }

        window.pdfjsLib.GlobalWorkerOptions.workerSrc =
            "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

        try {
            setLoadingMessage("LOADING DOCUMENT");
            setStatus("LOADING");

            const loadingTask = window.pdfjsLib.getDocument({
                url: root.dataset.pdfUrl,
            });

            pdfDocument = await loadingTask.promise;

            if (elements.pageCount) {
                elements.pageCount.textContent = String(pdfDocument.numPages);
            }

            if (elements.pageTotal) {
                elements.pageTotal.textContent = String(pdfDocument.numPages);
            }

            if (elements.pageInput) {
                elements.pageInput.max = String(pdfDocument.numPages);
                elements.pageInput.value = "1";
            }

            setControlsEnabled(true);
            updatePageControls();

            await renderPage();
        } catch (error) {
            console.error("Aether PDF load error:", error);

            const message = error && error.name === "InvalidPDFException"
                ? "The file is not a valid PDF document."
                : "Unable to load the PDF. The file may be unavailable or access may have been denied.";

            showError(message);
        }
    }

    if (elements.previous) {
        elements.previous.addEventListener("click", () => {
            goToPage(currentPage - 1);
        });
    }

    if (elements.next) {
        elements.next.addEventListener("click", () => {
            goToPage(currentPage + 1);
        });
    }

    if (elements.pageInput) {
        elements.pageInput.addEventListener("change", () => {
            goToPage(Number(elements.pageInput.value));
        });

        elements.pageInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                goToPage(Number(elements.pageInput.value));
                elements.pageInput.blur();
            }
        });
    }

    if (elements.zoomOut) {
        elements.zoomOut.addEventListener("click", () => {
            changeZoom(-ZOOM_STEP);
        });
    }

    if (elements.zoomIn) {
        elements.zoomIn.addEventListener("click", () => {
            changeZoom(ZOOM_STEP);
        });
    }

    if (elements.fit) {
        elements.fit.addEventListener("click", fitPageToWidth);
    }

    if (elements.fullscreen) {
        elements.fullscreen.addEventListener("click", toggleFullscreen);
    }

    document.addEventListener("fullscreenchange", updateFullscreenLabel);

    window.addEventListener("resize", () => {
        if (!fitWidth || !pdfDocument) {
            return;
        }

        cancelAnimationFrame(resizeFrame);

        resizeFrame = requestAnimationFrame(() => {
            renderPage();
        });
    });

    document.addEventListener("keydown", (event) => {
        if (!pdfDocument || event.altKey || event.ctrlKey || event.metaKey) {
            return;
        }

        const target = event.target;

        if (
            target instanceof HTMLInputElement ||
            target instanceof HTMLTextAreaElement ||
            target instanceof HTMLSelectElement ||
            target.isContentEditable
        ) {
            return;
        }

        switch (event.key) {
            case "ArrowLeft":
            case "PageUp":
                event.preventDefault();
                goToPage(currentPage - 1);
                break;

            case "ArrowRight":
            case "PageDown":
                event.preventDefault();
                goToPage(currentPage + 1);
                break;

            case "+":
            case "=":
                event.preventDefault();
                changeZoom(ZOOM_STEP);
                break;

            case "-":
            case "_":
                event.preventDefault();
                changeZoom(-ZOOM_STEP);
                break;

            case "f":
            case "F":
                event.preventDefault();
                toggleFullscreen();
                break;
        }
    });

    initialize();
})();
