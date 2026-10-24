
/* =========================================================
   Aether OS — Text Viewer
   ========================================================= */

(function () {
    "use strict";

    const root = document.querySelector("[data-text-viewer]");

    if (!root) {
        return;
    }


    const tag = root.querySelector("[data-text-tag]");
    const filename = root.dataset.textFilename || "";

    if (tag) {
        const match = filename.match(/\.([^.\/\\]+)$/);
        const extension = match ? match[1].toUpperCase() : "TXT";
        tag.textContent = `[TEXT.${extension}]`;
    }


    const contentUrl = root.dataset.textUrl;

    const viewport = root.querySelector("[data-text-viewport]");
    const loading = root.querySelector("[data-text-loading]");
    const loadingMessage = root.querySelector(
        "[data-text-loading-message]"
    );
    const errorPanel = root.querySelector("[data-text-error]");
    const errorMessage = root.querySelector(
        "[data-text-error-message]"
    );
    const documentPanel = root.querySelector("[data-text-document]");
    const contentElement = root.querySelector("[data-text-content]");

    const statusElement = root.querySelector("[data-text-status]");
    const encodingElement = root.querySelector("[data-text-encoding]");
    const linesElement = root.querySelector("[data-text-lines]");
    const sizeElement = root.querySelector("[data-text-size]");

    const copyButton = root.querySelector("[data-text-copy]");
    const fullscreenButton = root.querySelector(
        "[data-text-fullscreen]"
    );

    const zoomOutButton = root.querySelector("[data-text-zoom-out]");
    const zoomInButton = root.querySelector("[data-text-zoom-in]");
    const zoomResetButton = root.querySelector(
        "[data-text-zoom-reset]"
    );
    const zoomValue = root.querySelector("[data-text-zoom-value]");

    const BASE_FONT_SIZE = 12;
    const MIN_FONT_SIZE = 8;
    const MAX_FONT_SIZE = 24;
    const FONT_STEP = 1;

    let fontSize = BASE_FONT_SIZE;
    let loadedText = "";
    let loaded = false;

    function setStatus(value) {
        statusElement.textContent = value;
    }

    function showError(message) {
        loading.hidden = true;
        documentPanel.hidden = true;
        errorPanel.hidden = false;
        errorMessage.textContent = message;
        setStatus("ERROR");
    }

    const formatBytes = Aether.formatSize;

    function countLines(text) {
        if (text.length === 0) {
            return 0;
        }

        return text.split(/\r\n|\r|\n/).length;
    }

    /*
     * Decode text without interpreting it as HTML.
     *
     * BOM is checked first. Otherwise UTF-8 is attempted strictly.
     * If UTF-8 is invalid, try UTF-16 and then common legacy encodings.
     */
    function decodeText(buffer, declaredCharset) {
        const bytes = new Uint8Array(buffer);

        if (
            bytes.length >= 3 &&
            bytes[0] === 0xEF &&
            bytes[1] === 0xBB &&
            bytes[2] === 0xBF
        ) {
            return {
                text: new TextDecoder("utf-8").decode(bytes),
                encoding: "UTF-8 BOM"
            };
        }

        if (
            bytes.length >= 2 &&
            bytes[0] === 0xFF &&
            bytes[1] === 0xFE
        ) {
            return {
                text: new TextDecoder("utf-16le").decode(bytes),
                encoding: "UTF-16 LE"
            };
        }

        if (
            bytes.length >= 2 &&
            bytes[0] === 0xFE &&
            bytes[1] === 0xFF
        ) {
            return {
                text: new TextDecoder("utf-16be").decode(bytes),
                encoding: "UTF-16 BE"
            };
        }

        const candidates = [];

        if (declaredCharset) {
            candidates.push(declaredCharset);
        }

        candidates.push(
            "utf-8",
            "utf-16le",
            "utf-16be"
        );

        const tried = new Set();

        for (const encoding of candidates) {
            const normalized = encoding.toLowerCase();

            if (tried.has(normalized)) {
                continue;
            }

            tried.add(normalized);

            try {
                const decoder = new TextDecoder(encoding, {
                    fatal: true
                });

                return {
                    text: decoder.decode(bytes),
                    encoding: decoder.encoding.toUpperCase()
                };
            } catch (error) {
                // Try the next supported encoding.
            }
        }

        /*
         * A legacy single-byte encoding is a final fallback.
         * Windows-1252 is widely supported by browsers.
         */
        try {
            return {
                text: new TextDecoder("windows-1252").decode(bytes),
                encoding: "WINDOWS-1252*"
            };
        } catch (error) {
            throw new Error("The file could not be decoded as text.");
        }
    }

    function updateZoom() {
        contentElement.style.fontSize = `${fontSize}px`;
        zoomValue.textContent = `${Math.round(
            (fontSize / BASE_FONT_SIZE) * 100
        )}%`;

        zoomOutButton.disabled = !loaded || fontSize <= MIN_FONT_SIZE;
        zoomInButton.disabled = !loaded || fontSize >= MAX_FONT_SIZE;
        zoomResetButton.disabled = !loaded || fontSize === BASE_FONT_SIZE;
    }

    function enableControls() {
        copyButton.disabled = false;
        fullscreenButton.disabled = false;
        zoomOutButton.disabled = false;
        zoomInButton.disabled = false;
        zoomResetButton.disabled = false;

        updateZoom();
    }

    async function loadDocument() {
        if (!contentUrl) {
            showError("The document content URL is missing.");
            return;
        }

        setStatus("LOADING");
        loading.hidden = false;
        errorPanel.hidden = true;
        documentPanel.hidden = true;
        loadingMessage.textContent = "LOADING DOCUMENT";

        try {
            const response = await fetch(contentUrl, {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "Accept": "text/plain, */*"
                },
                cache: "no-store"
            });

            if (!response.ok) {
                const body = await response.text();

                console.error("Text Viewer HTTP error:", {
                    status: response.status,
                    url: response.url,
                    headers: Object.fromEntries(response.headers.entries()),
                    body: body.slice(0, 3000)
                });

                throw new Error(
                    `HTTP ${response.status}: ${body.slice(0, 300)}`
                );
            }

            const buffer = await response.arrayBuffer();

            const contentType =
                response.headers.get("Content-Type") || "";

            const charsetMatch = contentType.match(
                /charset\s*=\s*["']?([^;"'\s]+)/i
            );

            const declaredCharset = charsetMatch
                ? charsetMatch[1]
                : null;

            const decoded = decodeText(buffer, declaredCharset);

            loadedText = decoded.text;
            loaded = true;

            /*
             * textContent is intentional: file contents must never be
             * interpreted as HTML or executed as markup.
             */
            contentElement.textContent = loadedText;

            encodingElement.textContent = decoded.encoding;
            linesElement.textContent = countLines(loadedText).toLocaleString();
            sizeElement.textContent = formatBytes(buffer.byteLength);

            loading.hidden = true;
            errorPanel.hidden = true;
            documentPanel.hidden = false;

            setStatus("READY");
            enableControls();
        } catch (error) {
            console.error("Text Viewer:", error);

            showError(
                error instanceof Error
                    ? error.message
                    : "Unable to load text document."
            );
        }
    }

    zoomOutButton.addEventListener("click", function () {
        fontSize = Math.max(MIN_FONT_SIZE, fontSize - FONT_STEP);
        updateZoom();
    });

    zoomInButton.addEventListener("click", function () {
        fontSize = Math.min(MAX_FONT_SIZE, fontSize + FONT_STEP);
        updateZoom();
    });

    zoomResetButton.addEventListener("click", function () {
        fontSize = BASE_FONT_SIZE;
        updateZoom();
    });

    copyButton.addEventListener("click", async function () {
        if (!loaded) {
            return;
        }

        try {
            await navigator.clipboard.writeText(loadedText);
            setStatus("COPIED");

            window.setTimeout(function () {
                if (loaded) {
                    setStatus("READY");
                }
            }, 1500);
        } catch (error) {
            /*
             * Clipboard API may be unavailable in an insecure context.
             * The text remains selectable for manual copying.
             */
            setStatus("COPY FAILED");
        }
    });

    fullscreenButton.addEventListener("click", function () {
        Aether.toggleFullscreen(root);
    });

    document.addEventListener("fullscreenchange", function () {
        fullscreenButton.textContent = document.fullscreenElement
            ? "EXIT FULLSCREEN"
            : "FULLSCREEN";
    });

    /*
     * Prevent a click inside the document from propagating to any
     * parent desktop interaction handlers.
     */
    viewport.addEventListener("click", function (event) {
        event.stopPropagation();
    });

    updateZoom();
    loadDocument();
})();
