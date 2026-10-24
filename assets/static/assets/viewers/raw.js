/* =========================================================
   Aether OS — Raw / Binary Viewer
   ========================================================= */

(function () {
    "use strict";

    const root = document.querySelector("[data-raw-viewer]");

    if (!root) {
        return;
    }

    const contentUrl = root.dataset.rawUrl;

    const PAGE_SIZE = 256;
    // HEX bytes are visually grouped; keep in sync with raw.css.
    const GROUP_SIZE = 8;
    const SCAN_CHUNK_SIZE = 1024 * 1024;
    const MAX_PATTERN_LENGTH = 4096;
    const MAX_MATCHES = 10000;
    const MAX_STRINGS = 5000;
    const MIN_STRING_LENGTH = 4;
    const MAX_DISPLAY_STRING_LENGTH = 2048;
    // A single printable run is split once it reaches this size,
    // so memory stays bounded on huge text-like files.
    const MAX_RUN_BYTES = 4096;
    const MIN_PANEL_WIDTH = 180;
    const SPLITTER_WIDTH = 6;

    const elements = {
        tag: root.querySelector("[data-viewer-tag]"),
        status: root.querySelector("[data-viewer-status]"),
        data: root.querySelector("[data-raw-data]"),
        size: root.querySelector("[data-raw-size]"),
        signature: root.querySelector("[data-raw-signature]"),
        page: root.querySelector("[data-raw-page]"),
        offsetInput: root.querySelector("[data-raw-offset-input]"),
        gotoForm: root.querySelector("[data-raw-goto-form]"),
        width: root.querySelector("[data-raw-width]"),
        prev: root.querySelector("[data-raw-prev]"),
        next: root.querySelector("[data-raw-next]"),
        refresh: root.querySelector("[data-raw-refresh]"),

        searchForm: root.querySelector("[data-raw-search-form]"),
        searchMode: root.querySelector("[data-raw-search-mode]"),
        searchInput: root.querySelector("[data-raw-search-input]"),
        findButton: root.querySelector("[data-raw-find]"),
        searchCount: root.querySelector("[data-raw-search-count]"),
        searchPrev: root.querySelector("[data-raw-search-prev]"),
        searchNext: root.querySelector("[data-raw-search-next]"),

        stringsButton: root.querySelector("[data-raw-strings]"),
        stringsPanel: root.querySelector("[data-raw-strings-panel]"),
        stringsCount: root.querySelector("[data-raw-strings-count]"),
        stringsResults: root.querySelector("[data-raw-strings-results]"),
        splitter: root.querySelector("[data-raw-splitter]")
    };

    const state = {
        size: 0,
        start: 0,
        width: 16,
        bytes: new Uint8Array(0),
        selected: null,
        loading: false,
        scanning: false,

        matches: [],
        totalMatches: 0,
        matchLength: 0,
        currentMatch: -1,
        searchPattern: new Uint8Array(0),
        searchStatus: "none", // none | scanning | done

        strings: [],
        totalStrings: 0,
        stringsTruncated: false,

        view: "hex"
    };

    let hexRatio = 0.62;
    let resizing = false;
    let activePointerId = null;

    /*
     * Two independent counters:
     *  - loadOp: page loads (HEX view). A newer load supersedes an older one.
     *  - scanOp: full-file scans (search / strings). A newer scan, or a
     *    reload, cancels the running scan.
     * Page loads must NOT cancel scans, otherwise `state.scanning`
     * would never be reset.
     */
    let loadOp = 0;
    let scanOp = 0;

    // How many bytes from the start of the file are used for format
    // detection (enough for the TAR signature at offset 257).
    const SIGNATURE_SAMPLE_SIZE = 512;

    const ascii = (text) => Array.from(text, ch => ch.charCodeAt(0));

    /*
     * Binary signatures (magic numbers).
     *   bytes     - expected bytes; null matches any byte
     *   offset    - where the pattern starts (default 0)
     *   minLength - the file must be at least this long (default: end of pattern)
     * The first match wins, so specific entries go before generic ones.
     */
    const signatures = [
        // Images
        { name: "PNG image", bytes: [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A] },
        { name: "JPEG image", bytes: [0xFF, 0xD8, 0xFF] },
        { name: "GIF image", bytes: ascii("GIF8") },
        { name: "WebP image", bytes: [...ascii("RIFF"), null, null, null, null, ...ascii("WEBP")] },
        { name: "HEIC image", offset: 4, bytes: ascii("ftypheic") },
        { name: "TIFF image", bytes: [0x49, 0x49, 0x2A, 0x00] },
        { name: "TIFF image", bytes: [0x4D, 0x4D, 0x00, 0x2A] },
        { name: "BMP image", bytes: [0x42, 0x4D, null, null, null, null, 0x00, 0x00, 0x00, 0x00] },
        { name: "Photoshop document", bytes: ascii("8BPS") },

        // Audio / video
        { name: "WAV audio", bytes: [...ascii("RIFF"), null, null, null, null, ...ascii("WAVE")] },
        { name: "AVI video", bytes: [...ascii("RIFF"), null, null, null, null, ...ascii("AVI ")] },
        { name: "AIFF audio", bytes: [...ascii("FORM"), null, null, null, null, ...ascii("AIFF")] },
        { name: "M4A audio", offset: 4, bytes: ascii("ftypM4A ") },
        { name: "QuickTime video", offset: 4, bytes: ascii("ftypqt  ") },
        { name: "MP4 video", offset: 4, bytes: ascii("ftyp") },
        { name: "Matroska / WebM video", bytes: [0x1A, 0x45, 0xDF, 0xA3] },
        { name: "FLV video", bytes: [...ascii("FLV"), 0x01] },
        { name: "Ogg container", bytes: ascii("OggS") },
        { name: "FLAC audio", bytes: ascii("fLaC") },
        { name: "MP3 audio (ID3 tag)", bytes: ascii("ID3") },
        { name: "MP3 audio", bytes: [0xFF, 0xFB] },
        { name: "MP3 audio", bytes: [0xFF, 0xF3] },
        { name: "MP3 audio", bytes: [0xFF, 0xF2] },
        { name: "MIDI audio", bytes: ascii("MThd") },

        // Documents / keys
        { name: "PDF document", bytes: ascii("%PDF-") },
        { name: "PostScript document", bytes: ascii("%!PS") },
        { name: "RTF document", bytes: ascii("{\\rtf") },
        { name: "Legacy Office document (OLE2)", bytes: [0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1] },
        { name: "PEM key / certificate", bytes: ascii("-----BEGIN ") },

        // Archives
        { name: "ZIP archive (ZIP / DOCX / XLSX / APK)", bytes: [0x50, 0x4B, 0x03, 0x04] },
        { name: "ZIP archive (empty)", bytes: [0x50, 0x4B, 0x05, 0x06] },
        { name: "ZIP archive (spanned)", bytes: [0x50, 0x4B, 0x07, 0x08] },
        { name: "RAR archive", bytes: [0x52, 0x61, 0x72, 0x21, 0x1A, 0x07] },
        { name: "7-Zip archive", bytes: [0x37, 0x7A, 0xBC, 0xAF, 0x27, 0x1C] },
        { name: "XZ archive", bytes: [0xFD, 0x37, 0x7A, 0x58, 0x5A, 0x00] },
        { name: "Zstandard archive", bytes: [0x28, 0xB5, 0x2F, 0xFD] },
        { name: "LZ4 archive", bytes: [0x04, 0x22, 0x4D, 0x18] },
        { name: "BZIP2 archive", bytes: [...ascii("BZh"), null, 0x31, 0x41, 0x59, 0x26, 0x53, 0x59] },
        { name: "GZIP archive", bytes: [0x1F, 0x8B, 0x08] },
        { name: "TAR archive", offset: 257, bytes: ascii("ustar") },
        { name: "Cabinet archive (CAB)", bytes: ascii("MSCF") },

        // Executables / code
        { name: "ELF executable", bytes: [0x7F, 0x45, 0x4C, 0x46] },
        { name: "DOS / Windows executable", bytes: [0x4D, 0x5A], minLength: 64 },
        { name: "Mach-O executable", bytes: [0xFE, 0xED, 0xFA, 0xCE] },
        { name: "Mach-O executable", bytes: [0xFE, 0xED, 0xFA, 0xCF] },
        { name: "Mach-O executable", bytes: [0xCE, 0xFA, 0xED, 0xFE] },
        { name: "Mach-O executable", bytes: [0xCF, 0xFA, 0xED, 0xFE] },
        { name: "Java class / Mach-O universal binary", bytes: [0xCA, 0xFE, 0xBA, 0xBE] },
        { name: "WebAssembly module", bytes: [0x00, 0x61, 0x73, 0x6D] },
        { name: "Android DEX", bytes: [...ascii("dex"), 0x0A] },
        { name: "Windows shortcut (LNK)", bytes: [0x4C, 0x00, 0x00, 0x00, 0x01, 0x14, 0x02, 0x00] },
        { name: "Script (shebang)", bytes: ascii("#!") },

        // Databases / containers / misc
        { name: "SQLite database", bytes: ascii("SQLite format 3\0") },
        { name: "KeePass database (KDBX)", bytes: [0x03, 0xD9, 0xA2, 0x9A, 0x67, 0xFB, 0x4B, 0xB5] },
        { name: "LUKS encrypted volume", bytes: [...ascii("LUKS"), 0xBA, 0xBE] },
        { name: "Packet capture (PCAP)", bytes: [0xD4, 0xC3, 0xB2, 0xA1] },
        { name: "Packet capture (PCAP)", bytes: [0xA1, 0xB2, 0xC3, 0xD4] },
        { name: "Packet capture (PCAPNG)", bytes: [0x0A, 0x0D, 0x0D, 0x0A] },
        { name: "Apple binary plist", bytes: ascii("bplist00") },

        // Fonts
        { name: "TrueType font", bytes: [0x00, 0x01, 0x00, 0x00, 0x00] },
        { name: "OpenType font", bytes: ascii("OTTO") },
        { name: "WOFF font", bytes: ascii("wOFF") },
        { name: "WOFF2 font", bytes: ascii("wOF2") }
    ];

    /* =====================================================
       Basic helpers
       ===================================================== */

    function setStatus(message) {
        elements.status.textContent = message;
    }

    const formatSize = Aether.formatSize;

    function formatOffset(offset) {
        return offset.toString(16).toUpperCase().padStart(8, "0");
    }

    function printable(byte) {
        return byte >= 0x20 && byte <= 0x7E;
    }

    function matchesSignature(data, signature) {
        const offset = signature.offset || 0;
        const pattern = signature.bytes;
        const required = Math.max(
            offset + pattern.length,
            signature.minLength || 0
        );

        if (data.length < required) {
            return false;
        }

        for (let i = 0; i < pattern.length; i++) {
            if (pattern[i] !== null && data[offset + i] !== pattern[i]) {
                return false;
            }
        }

        return true;
    }

    function looksLikeJson(head) {
        return (
            /^\{\s*(?:["}]|$)/.test(head) ||
            /^\[\s*(?:[\[{"\]]|-?\d|true\b|false\b|null\b|$)/.test(head)
        );
    }

    /*
     * Text formats have no magic numbers, so they are recognised from the
     * first bytes of the content. Returns null when the sample is not text.
     * `wholeFile` tells whether the sample is the entire file; then JSON can
     * be verified by actually parsing it.
     */
    function detectText(data, wholeFile) {
        if (
            data.length >= 2 &&
            ((data[0] === 0xFF && data[1] === 0xFE) ||
                (data[0] === 0xFE && data[1] === 0xFF))
        ) {
            return "UTF-16 text";
        }

        const start =
            data[0] === 0xEF && data[1] === 0xBB && data[2] === 0xBF ? 3 : 0;

        let asciiOnly = true;

        for (let i = start; i < data.length; i++) {
            const byte = data[i];

            if (byte === 0x09 || byte === 0x0A || byte === 0x0C || byte === 0x0D) {
                continue;
            }

            if (byte < 0x20 || byte === 0x7F) {
                return null;
            }

            if (byte >= 0x80) {
                asciiOnly = false;
            }
        }

        let text;

        try {
            // stream: true tolerates a multi-byte character cut off at
            // the end of the sample.
            text = new TextDecoder("utf-8", { fatal: true }).decode(
                data.subarray(start),
                { stream: true }
            );
        } catch (error) {
            return null;
        }

        const head = text.trimStart();

        if (looksLikeJson(head)) {
            if (!wholeFile) {
                return "JSON text";
            }

            try {
                JSON.parse(text);
                return "JSON text";
            } catch (error) {
                // Not valid JSON after all: fall through to plain text.
            }
        }

        if (/^<\?xml\b/i.test(head)) {
            return /<svg\b/i.test(head) ? "SVG image" : "XML document";
        }

        if (/^<svg\b/i.test(head)) {
            return "SVG image";
        }

        if (/^<!doctype\s+html|^<html\b/i.test(head)) {
            return "HTML document";
        }

        if (/^<[a-z!?]/i.test(head)) {
            return "XML / HTML markup";
        }

        return asciiOnly ? "ASCII text" : "UTF-8 text";
    }

    function detectSignature(data, wholeFile) {
        if (data.length === 0) {
            return "Empty file";
        }

        for (const signature of signatures) {
            if (matchesSignature(data, signature)) {
                return signature.name;
            }
        }

        return detectText(data, wholeFile) || "Unknown";
    }

    function isStringsVisible() {
        return Boolean(
            elements.stringsPanel &&
            !elements.stringsPanel.hidden
        );
    }

    /* =====================================================
       Split view
       ===================================================== */

    function updateSplitLayout() {
        if (!elements.splitter || !elements.stringsPanel) {
            return;
        }

        const inspector = elements.splitter.parentElement;
        const visible = isStringsVisible();

        elements.splitter.hidden = !visible;

        if (!visible) {
            inspector.style.gridTemplateColumns = "";
            return;
        }

        const inspectorWidth = inspector.clientWidth;

        if (inspectorWidth <= 0) {
            return;
        }

        const splitterWidth = SPLITTER_WIDTH;
        const availableWidth = inspectorWidth - splitterWidth;

        if (availableWidth <= 0) {
            return;
        }

        const minRatio = Math.min(
            0.5,
            MIN_PANEL_WIDTH / availableWidth
        );

        hexRatio = Math.max(
            minRatio,
            Math.min(1 - minRatio, hexRatio)
        );

        inspector.style.gridTemplateColumns =
            `minmax(0, ${hexRatio}fr) ` +
            `${splitterWidth}px ` +
            `minmax(0, ${1 - hexRatio}fr)`;
    }

    function setStringsVisible(visible) {
        if (!elements.stringsPanel) {
            return;
        }

        elements.stringsPanel.hidden = !visible;

        if (elements.splitter) {
            elements.splitter.hidden = !visible;
        }

        if (visible) {
            state.view = "strings";

            requestAnimationFrame(updateSplitLayout);
        } else {
            state.view = "hex";

            if (elements.splitter) {
                elements.splitter.parentElement.style.gridTemplateColumns = "";
            }
        }
    }

    function startResize(event) {
        if (
            !elements.splitter ||
            !isStringsVisible() ||
            event.button !== 0
        ) {
            return;
        }

        resizing = true;
        activePointerId = event.pointerId;

        elements.splitter.setPointerCapture(event.pointerId);
        document.body.classList.add("rv-resizing");

        event.preventDefault();
    }

    function resizePanels(event) {
        if (!resizing || event.pointerId !== activePointerId) {
            return;
        }

        const inspector = elements.splitter.parentElement;
        const rect = inspector.getBoundingClientRect();
        const availableWidth = rect.width - SPLITTER_WIDTH;

        if (availableWidth <= 0) {
            return;
        }

        const pointerX = event.clientX - rect.left;
        const minRatio = Math.min(
            0.5,
            MIN_PANEL_WIDTH / availableWidth
        );

        hexRatio = Math.max(
            minRatio,
            Math.min(1 - minRatio, pointerX / availableWidth)
        );

        updateSplitLayout();
    }

    function stopResize(event) {
        if (!resizing) {
            return;
        }

        if (
            event &&
            activePointerId !== null &&
            event.pointerId !== undefined &&
            event.pointerId !== activePointerId
        ) {
            return;
        }

        resizing = false;
        activePointerId = null;
        document.body.classList.remove("rv-resizing");
    }

    if (elements.splitter) {
        elements.splitter.addEventListener("pointerdown", startResize);
        elements.splitter.addEventListener("pointermove", resizePanels);
        elements.splitter.addEventListener("pointerup", stopResize);
        elements.splitter.addEventListener("pointercancel", stopResize);
        elements.splitter.addEventListener("lostpointercapture", stopResize);

        elements.splitter.addEventListener("keydown", function (event) {
            if (
                event.key !== "ArrowLeft" &&
                event.key !== "ArrowRight"
            ) {
                return;
            }

            if (!isStringsVisible()) {
                return;
            }

            event.preventDefault();

            hexRatio += event.key === "ArrowLeft" ? -0.03 : 0.03;
            updateSplitLayout();
        });

        window.addEventListener("resize", updateSplitLayout);
    }

    /* =====================================================
       HTTP range requests
       ===================================================== */

    async function fetchRange(start, end) {
        const response = await fetch(contentUrl, {
            method: "GET",
            headers: {
                Range: `bytes=${start}-${end}`,
                "Accept-Encoding": "identity"
            },
            credentials: "same-origin",
            cache: "no-store"
        });

        if (response.status === 416) {
            throw new Error("Requested byte range is outside the file.");
        }

        if (response.status !== 206) {
            throw new Error(
                response.status === 200
                    ? "The server ignored the byte-range request."
                    : `The server returned HTTP ${response.status}.`
            );
        }

        const bytes = new Uint8Array(await response.arrayBuffer());
        const expectedLength = end - start + 1;

        if (bytes.length !== expectedLength) {
            throw new Error(
                `Incomplete range response: expected ${expectedLength} bytes, received ${bytes.length}.`
            );
        }

        return bytes;
    }

    async function loadMetadata() {
        const response = await fetch(contentUrl, {
            method: "HEAD",
            credentials: "same-origin",
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error(
                `Unable to read file metadata: HTTP ${response.status}.`
            );
        }

        const length = response.headers.get("Content-Length");

        if (length === null || !/^\d+$/.test(length)) {
            throw new Error("The server did not provide a valid file size.");
        }

        state.size = Number(length);

        if (!Number.isSafeInteger(state.size)) {
            throw new Error("The file size exceeds the supported offset range.");
        }

        elements.size.textContent = formatSize(state.size);
    }

    async function loadSignature() {
        if (state.size === 0) {
            elements.signature.textContent = "Empty file";
            return;
        }

        const sampleSize = Math.min(SIGNATURE_SAMPLE_SIZE, state.size);
        const bytes = await fetchRange(0, sampleSize - 1);

        elements.signature.textContent = detectSignature(
            bytes,
            state.size <= SIGNATURE_SAMPLE_SIZE
        );
    }

    /* =====================================================
       HEX renderer
       ===================================================== */

    function getVisibleMatchBytes() {
        const offsets = new Set();
        const pageEnd = state.start + state.bytes.length;

        for (const matchOffset of state.matches) {
            const matchEnd = matchOffset + state.matchLength;

            if (matchEnd <= state.start) {
                continue;
            }

            if (matchOffset >= pageEnd) {
                break;
            }

            const from = Math.max(matchOffset, state.start);
            const to = Math.min(matchEnd, pageEnd);

            for (let offset = from; offset < to; offset++) {
                offsets.add(offset);
            }
        }

        return offsets;
    }

    function makeByte(value, offset, type, matchBytes) {
        const element = document.createElement("span");

        element.className = type;
        element.dataset.offset = String(offset);

        element.textContent = type === "rv-byte"
            ? value.toString(16).toUpperCase().padStart(2, "0")
            : (printable(value) ? String.fromCharCode(value) : ".");

        if (type === "rv-byte" && value === 0) {
            element.classList.add("is-zero");
        }

        if (type === "rv-char" && !printable(value)) {
            element.classList.add("is-nonprintable");
        }

        if (matchBytes.has(offset)) {
            element.classList.add("is-match");
        }

        if (state.selected === offset) {
            element.classList.add("is-selected");
        }

        element.title =
            `Offset 0x${formatOffset(offset)} · 0x${value
                .toString(16)
                .toUpperCase()
                .padStart(2, "0")}`;

        return element;
    }

    // Scrolls the HEX panel so the selected byte is centred; a freshly
    // loaded page without a selection starts at the top.
    function revealSelected() {
        const container = elements.data;
        const target = container.querySelector(".rv-byte.is-selected");

        if (!target) {
            container.scrollTop = 0;
            return;
        }

        const box = container.getBoundingClientRect();
        const rect = target.getBoundingClientRect();

        container.scrollTop +=
            rect.top - box.top - (box.height - rect.height) / 2;
    }

    // Tells the CSS how many bytes per row / how many group gaps there are,
    // so the header and all rows share one fixed HEX column width.
    function updateHexGeometry() {
        root.style.setProperty("--rv-bytes", String(state.width));
        root.style.setProperty(
            "--rv-groups",
            String(Math.max(0, Math.ceil(state.width / GROUP_SIZE) - 1))
        );
    }

    function render(reveal = false) {
        updateHexGeometry();
        elements.data.replaceChildren();

        if (state.size === 0) {
            const message = document.createElement("div");
            message.className = "rv-message";
            message.textContent = "EMPTY FILE";
            elements.data.appendChild(message);
            return;
        }

        if (state.bytes.length === 0) {
            const message = document.createElement("div");
            message.className = "rv-message";
            message.textContent = "NO DATA";
            elements.data.appendChild(message);
            return;
        }

        const matchBytes = getVisibleMatchBytes();
        const fragment = document.createDocumentFragment();

        for (
            let index = 0;
            index < state.bytes.length;
            index += state.width
        ) {
            const row = document.createElement("div");
            row.className = "rv-row";

            const offset = state.start + index;
            const offsetElement = document.createElement("span");

            offsetElement.className = "rv-offset";
            offsetElement.textContent = formatOffset(offset);

            const hex = document.createElement("span");
            hex.className = "rv-hex";

            const ascii = document.createElement("span");
            ascii.className = "rv-ascii";

            const end = Math.min(
                index + state.width,
                state.bytes.length
            );

            for (let i = index; i < end; i++) {
                const byte = state.bytes[i];
                const absoluteOffset = state.start + i;

                const hexByte = makeByte(
                    byte,
                    absoluteOffset,
                    "rv-byte",
                    matchBytes
                );

                // Gap after every 8th byte, but not after the last one.
                if (
                    (i - index) % GROUP_SIZE === GROUP_SIZE - 1 &&
                    i < index + state.width - 1
                ) {
                    hexByte.classList.add("is-group-end");
                }

                hex.appendChild(hexByte);

                ascii.appendChild(
                    makeByte(byte, absoluteOffset, "rv-char", matchBytes)
                );
            }

            row.append(offsetElement, hex, ascii);
            fragment.appendChild(row);
        }

        elements.data.appendChild(fragment);

        elements.page.textContent =
            `${formatOffset(state.start)}–${formatOffset(
                state.start + state.bytes.length - 1
            )}`;

        elements.prev.disabled = state.start === 0;
        elements.next.disabled =
            state.start + state.bytes.length >= state.size;

        if (reveal) {
            revealSelected();
        }
    }

    async function loadPage(requestedOffset) {
        // A newer request supersedes an older one (see loadOp), so rapid
        // clicks never leave the page out of sync with the UI state.
        const thisLoad = ++loadOp;
        state.loading = true;
        setStatus("READING");

        try {
            if (state.size === 0) {
                state.start = 0;
                state.bytes = new Uint8Array(0);
                render();
                setStatus("READY");
                return;
            }

            const maxStart = Math.floor(
                (state.size - 1) / PAGE_SIZE
            ) * PAGE_SIZE;

            state.start = Math.min(
                Math.max(0, requestedOffset),
                maxStart
            );

            state.start = Math.floor(state.start / PAGE_SIZE) * PAGE_SIZE;

            const end = Math.min(
                state.start + PAGE_SIZE - 1,
                state.size - 1
            );

            const bytes = await fetchRange(state.start, end);

            if (thisLoad !== loadOp) {
                return;
            }

            state.bytes = bytes;

            if (state.selected !== null) {
                const pageEnd = state.start + state.bytes.length - 1;

                if (
                    state.selected < state.start ||
                    state.selected > pageEnd
                ) {
                    state.selected = null;
                }
            }

            render(true);
            setStatus("READY");
        } catch (error) {
            if (thisLoad !== loadOp) {
                return;
            }

            state.bytes = new Uint8Array(0);
            render();
            setStatus("ERROR");

            const message = document.createElement("div");
            message.className = "rv-message";
            message.textContent =
                error.message || "Unable to load file data.";

            elements.data.appendChild(message);
        } finally {
            if (thisLoad === loadOp) {
                state.loading = false;
            }
        }
    }

    function parseOffset(value) {
        const cleaned = value.trim().replace(/^0x/i, "");

        if (!/^[0-9a-f]+$/i.test(cleaned)) {
            return null;
        }

        const offset = Number.parseInt(cleaned, 16);

        return Number.isSafeInteger(offset) ? offset : null;
    }

    /* =====================================================
       Search
       ===================================================== */

    // Accepts "41 45 54", "41-45-54", "41:45:54", "0x41 0x45 0x54"
    // and contiguous digits such as "414554" (read as pairs).
    function parseHexPattern(value) {
        const cleaned = value.trim().replace(/0x/gi, "");

        if (!cleaned || !/^[0-9a-f\s,:-]+$/i.test(cleaned)) {
            return null;
        }

        const tokens = [];

        for (const token of cleaned.split(/[\s,:-]+/).filter(Boolean)) {
            if (token.length <= 2) {
                tokens.push(token);
            } else if (token.length % 2 === 0) {
                tokens.push(...token.match(/../g));
            } else {
                return null;
            }
        }

        if (!tokens.length) {
            return null;
        }

        return Uint8Array.from(tokens, token => Number.parseInt(token, 16));
    }

    function parseSearchPattern() {
        const value = elements.searchInput.value;

        if (elements.searchMode.value === "hex") {
            const pattern = parseHexPattern(value);

            if (!pattern) {
                throw new Error(
                    "Invalid HEX pattern. Use bytes like 41 45 54 48 45 52."
                );
            }

            return pattern;
        }

        if (!value.length) {
            throw new Error("Enter text to search for.");
        }

        return new TextEncoder().encode(value);
    }

    function updateSearchControls() {
        const hasMatches = state.matches.length > 0;

        elements.searchPrev.disabled =
            state.scanning || !hasMatches || state.currentMatch <= 0;

        elements.searchNext.disabled =
            state.scanning ||
            !hasMatches ||
            state.currentMatch < 0 ||
            state.currentMatch >= state.matches.length - 1;

        elements.findButton.disabled = state.scanning;
        elements.stringsButton.disabled = state.scanning;

        if (state.totalMatches === 0) {
            // Neutral until a search has actually been run.
            elements.searchCount.textContent =
                state.searchStatus === "scanning"
                    ? "SCANNING..."
                    : state.searchStatus === "done"
                        ? "NO MATCHES"
                        : "—";
        } else {
            const stored = state.matches.length;
            const total = state.totalMatches;
            const suffix = total > stored ? "+" : "";

            elements.searchCount.textContent =
                `${state.currentMatch >= 0 ? state.currentMatch + 1 : "—"} / ${total}${suffix}`;
        }
    }

    async function scanFile(onChunk, isCancelled) {
        let start = 0;

        while (start < state.size) {
            if (isCancelled && isCancelled()) {
                return false;
            }

            const end = Math.min(
                start + SCAN_CHUNK_SIZE - 1,
                state.size - 1
            );

            const bytes = await fetchRange(start, end);

            if (isCancelled && isCancelled()) {
                return false;
            }

            await onChunk(bytes, start, end);

            start = end + 1;

            const progress = state.size
                ? Math.floor((start / state.size) * 100)
                : 100;

            setStatus(`SCANNING ${progress}%`);
        }

        return true;
    }

    async function runSearch() {
        if (state.scanning || state.loading) {
            return;
        }

        let pattern;

        try {
            pattern = parseSearchPattern();
        } catch (error) {
            setStatus("INVALID PATTERN");
            elements.searchCount.textContent = error.message;
            return;
        }

        if (pattern.length > MAX_PATTERN_LENGTH) {
            setStatus("PATTERN TOO LONG");
            elements.searchCount.textContent =
                `Maximum pattern length: ${MAX_PATTERN_LENGTH} bytes.`;
            return;
        }

        const thisScan = ++scanOp;
        const isCancelled = () => thisScan !== scanOp;

        state.scanning = true;
        state.matches = [];
        state.totalMatches = 0;
        state.matchLength = pattern.length;
        state.searchPattern = pattern;
        state.searchStatus = "scanning";
        state.currentMatch = -1;
        state.selected = null;

        updateSearchControls();
        setStatus("SEARCHING");

        try {
            let carry = new Uint8Array(0);

            const completed = await scanFile(
                async (chunk, chunkStart) => {
                    const combined = new Uint8Array(
                        carry.length + chunk.length
                    );

                    combined.set(carry, 0);
                    combined.set(chunk, carry.length);

                    const combinedStart = chunkStart - carry.length;

                    for (
                        let i = 0;
                        i <= combined.length - pattern.length;
                        i++
                    ) {
                        let found = true;

                        for (let j = 0; j < pattern.length; j++) {
                            if (combined[i + j] !== pattern[j]) {
                                found = false;
                                break;
                            }
                        }

                        if (!found) {
                            continue;
                        }

                        const offset = combinedStart + i;

                        // Ignore matches already completely processed
                        // in the previous chunk.
                        if (
                            chunkStart > 0 &&
                            offset + pattern.length <= chunkStart
                        ) {
                            continue;
                        }

                        state.totalMatches++;

                        if (state.matches.length < MAX_MATCHES) {
                            state.matches.push(offset);
                        }
                    }

                    const carryLength = Math.min(
                        pattern.length - 1,
                        combined.length
                    );

                    carry = combined.slice(
                        combined.length - carryLength
                    );
                },
                isCancelled
            );

            if (!completed || isCancelled()) {
                return;
            }

            // The scan itself is over: unlock the controls before
            // navigating to the first match.
            state.scanning = false;
            state.searchStatus = "done";
            state.currentMatch = state.matches.length ? 0 : -1;
            updateSearchControls();

            if (state.matches.length) {
                setStatus(
                    state.totalMatches > MAX_MATCHES
                        ? "SEARCH COMPLETE · RESULTS CAPPED"
                        : "SEARCH COMPLETE"
                );

                await goToMatch(0);
            } else {
                if (isStringsVisible()) {
                    renderStrings();
                }

                render();
                setStatus("NO MATCHES");
            }
        } catch (error) {
            if (isCancelled()) {
                return;
            }

            state.searchStatus = "none";
            setStatus("SEARCH ERROR");
            elements.searchCount.textContent =
                error.message || "Unable to search file.";
        } finally {
            if (!isCancelled()) {
                state.scanning = false;
                updateSearchControls();
            }
        }
    }

    async function goToMatch(index) {
        if (index < 0 || index >= state.matches.length) {
            return;
        }

        state.currentMatch = index;
        state.selected = state.matches[index];
        elements.offsetInput.value = formatOffset(state.selected);

        updateSearchControls();

        await loadPage(state.selected);

        // Keep STRINGS open and refresh its search highlighting.
        if (isStringsVisible()) {
            renderStrings();
        }
    }

    /* =====================================================
       STRINGS renderer and search highlighting
       ===================================================== */

    // The string that was actually searched for (bytes decoded as UTF-8),
    // or null when the pattern is not valid text. Matching is exact, the
    // same as the byte search itself.
    function getStringSearchPattern() {
        if (!state.searchPattern || state.searchPattern.length === 0) {
            return null;
        }

        try {
            return new TextDecoder("utf-8", { fatal: true }).decode(
                state.searchPattern
            );
        } catch (error) {
            return null;
        }
    }

    function appendHighlightedText(container, value, pattern) {
        if (!pattern) {
            container.textContent = value;
            return;
        }

        let cursor = 0;

        while (cursor < value.length) {
            const index = value.indexOf(pattern, cursor);

            if (index === -1) {
                container.appendChild(
                    document.createTextNode(value.slice(cursor))
                );
                break;
            }

            if (index > cursor) {
                container.appendChild(
                    document.createTextNode(value.slice(cursor, index))
                );
            }

            const mark = document.createElement("mark");
            mark.className = "rv-string-match";
            mark.textContent = value.slice(
                index,
                index + pattern.length
            );

            container.appendChild(mark);
            cursor = index + pattern.length;
        }
    }

    function renderStrings() {
        elements.stringsResults.replaceChildren();

        const fragment = document.createDocumentFragment();
        const pattern = getStringSearchPattern();

        for (const item of state.strings) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "rv-string-row";
            button.dataset.stringOffset = String(item.offset);

            const offset = document.createElement("span");
            offset.className = "rv-string-offset";
            offset.textContent = formatOffset(item.offset);

            const value = document.createElement("span");
            value.className = "rv-string-value";

            appendHighlightedText(value, item.value, pattern);

            button.append(offset, value);
            fragment.appendChild(button);
        }

        elements.stringsResults.appendChild(fragment);

        if (state.strings.length === 0) {
            const message = document.createElement("div");
            message.className = "rv-message";
            message.textContent = "NO STRINGS FOUND";
            elements.stringsResults.appendChild(message);
        }

        const suffix = state.stringsTruncated ? "+" : "";
        elements.stringsCount.textContent =
            `${state.totalStrings}${suffix} FOUND`;
    }

    /* =====================================================
       STRINGS extraction
       ===================================================== */

    async function runStrings() {
        if (state.scanning || state.loading) {
            return;
        }

        const thisScan = ++scanOp;
        const isCancelled = () => thisScan !== scanOp;

        state.scanning = true;
        state.strings = [];
        state.totalStrings = 0;
        state.stringsTruncated = false;

        setStringsVisible(true);

        elements.stringsResults.replaceChildren();

        const loading = document.createElement("div");
        loading.className = "rv-message";
        loading.textContent = "SCANNING FILE FOR PRINTABLE STRINGS...";
        elements.stringsResults.appendChild(loading);

        updateSearchControls();
        setStatus("EXTRACTING STRINGS");

        // Current run of printable characters (fixed buffer).
        const run = new Uint8Array(MAX_RUN_BYTES);
        let runLength = 0;
        let runChars = 0;
        let runStart = 0;

        // Current character being assembled. A multi-byte UTF-8
        // sequence may span two scan chunks, so this state lives here.
        const seq = new Uint8Array(4);
        let seqLength = 0;
        let seqNeed = 0;
        let seqStart = 0;

        function finishRun() {
            if (runChars >= MIN_STRING_LENGTH) {
                state.totalStrings++;

                if (state.strings.length < MAX_STRINGS) {
                    const value = new TextDecoder("utf-8", {
                        fatal: false
                    }).decode(run.subarray(0, runLength));

                    state.strings.push({
                        offset: runStart,
                        value: value.slice(0, MAX_DISPLAY_STRING_LENGTH)
                    });
                } else {
                    state.stringsTruncated = true;
                }
            }

            runLength = 0;
            runChars = 0;
        }

        // Appends the complete character stored in seq[0..length).
        function appendChar(length, offset) {
            if (runLength + length > MAX_RUN_BYTES) {
                finishRun();
            }

            if (runLength === 0) {
                runStart = offset;
            }

            run.set(seq.subarray(0, length), runLength);
            runLength += length;
            runChars++;
        }

        function startSequence(first, need, offset) {
            seq[0] = first;
            seqLength = 1;
            seqNeed = need;
            seqStart = offset;
        }

        /*
         * Accepts printable ASCII and well-formed UTF-8 only.
         * Stray bytes >= 0x80 (typical for PNG, ZIP, executables)
         * end the current run instead of being treated as text.
         */
        function consumeByte(byte, offset) {
            if (seqNeed > 0) {
                if ((byte & 0xC0) === 0x80) {
                    seq[seqLength++] = byte;
                    seqNeed--;

                    if (seqNeed === 0) {
                        appendChar(seqLength, seqStart);
                        seqLength = 0;
                    }

                    return;
                }

                // Broken sequence: drop it and end the run,
                // then handle this byte as a fresh one.
                seqNeed = 0;
                seqLength = 0;
                finishRun();
            }

            if ((byte >= 0x20 && byte <= 0x7E) || byte === 0x09) {
                seq[0] = byte;
                appendChar(1, offset);
            } else if (byte >= 0xC2 && byte <= 0xDF) {
                startSequence(byte, 1, offset);
            } else if (byte >= 0xE0 && byte <= 0xEF) {
                startSequence(byte, 2, offset);
            } else if (byte >= 0xF0 && byte <= 0xF4) {
                startSequence(byte, 3, offset);
            } else {
                finishRun();
            }
        }

        try {
            const completed = await scanFile(
                async (bytes, chunkStart) => {
                    for (let i = 0; i < bytes.length; i++) {
                        consumeByte(bytes[i], chunkStart + i);
                    }
                },
                isCancelled
            );

            if (!completed || isCancelled()) {
                return;
            }

            finishRun();
            renderStrings();

            setStatus(
                state.stringsTruncated
                    ? "STRINGS COMPLETE · RESULTS CAPPED"
                    : "STRINGS COMPLETE"
            );
        } catch (error) {
            if (isCancelled()) {
                return;
            }

            elements.stringsResults.replaceChildren();

            const message = document.createElement("div");
            message.className = "rv-message";
            message.textContent =
                error.message || "Unable to extract strings.";

            elements.stringsResults.appendChild(message);
            setStatus("STRINGS ERROR");
        } finally {
            if (!isCancelled()) {
                state.scanning = false;
                updateSearchControls();
                updateSplitLayout();
            }
        }
    }

    /* =====================================================
       Event handlers
       ===================================================== */

    elements.gotoForm.addEventListener("submit", function (event) {
        event.preventDefault();

        const offset = parseOffset(elements.offsetInput.value);

        if (offset === null) {
            setStatus("INVALID OFFSET");
            return;
        }

        if (offset >= state.size && state.size !== 0) {
            setStatus("OFFSET OUT OF RANGE");
            return;
        }

        state.selected = offset;
        loadPage(offset);
    });

    elements.width.addEventListener("change", function () {
        state.width = Number(elements.width.value) || 16;
        render();
    });

    elements.prev.addEventListener("click", function () {
        loadPage(state.start - PAGE_SIZE);
    });

    elements.next.addEventListener("click", function () {
        loadPage(state.start + PAGE_SIZE);
    });

    elements.refresh.addEventListener("click", initialize);

    elements.data.addEventListener("click", function (event) {
        const byteElement = event.target.closest("[data-offset]");

        if (!byteElement) {
            return;
        }

        state.selected = Number(byteElement.dataset.offset);
        elements.offsetInput.value = formatOffset(state.selected);

        render();
    });

    elements.searchForm.addEventListener("submit", function (event) {
        event.preventDefault();
        runSearch();
    });

    elements.searchMode.addEventListener("change", function () {
        elements.searchInput.placeholder =
            elements.searchMode.value === "hex"
                ? "Example: 41 45 54 48 45 52"
                : "Text to find...";
    });

    elements.searchPrev.addEventListener("click", function () {
        goToMatch(state.currentMatch - 1);
    });

    elements.searchNext.addEventListener("click", function () {
        goToMatch(state.currentMatch + 1);
    });

    elements.stringsButton.addEventListener("click", runStrings);

    elements.stringsResults.addEventListener("click", function (event) {
        const button = event.target.closest("[data-string-offset]");

        if (!button) {
            return;
        }

        const offset = Number(button.dataset.stringOffset);

        if (!Number.isSafeInteger(offset)) {
            return;
        }

        state.selected = offset;
        elements.offsetInput.value = formatOffset(offset);

        // Do not hide the STRINGS panel when jumping to a string.
        loadPage(offset);
    });

    /* =====================================================
       Initialization
       ===================================================== */

    async function initialize() {
        // RELOAD cancels a running scan instead of being blocked by it.
        ++scanOp;
        state.scanning = false;

        state.start = 0;
        state.selected = null;
        state.bytes = new Uint8Array(0);

        state.matches = [];
        state.totalMatches = 0;
        state.matchLength = 0;
        state.searchPattern = new Uint8Array(0);
        state.searchStatus = "none";
        state.currentMatch = -1;

        state.strings = [];
        state.totalStrings = 0;
        state.stringsTruncated = false;
        state.view = "hex";

        setStringsVisible(false);

        elements.data.replaceChildren();
        elements.searchCount.textContent = "—";
        elements.stringsCount.textContent = "—";

        updateSearchControls();
        elements.searchPrev.disabled = true;
        elements.searchNext.disabled = true;
        elements.searchCount.textContent = "—";

        // The file name / extension is deliberately not shown anywhere:
        // the format must be discovered from the content itself.
        elements.tag.textContent = "[RAW]";
        elements.signature.textContent = "—";
        elements.size.textContent = "—";
        elements.page.textContent = "—";
        setStatus("INITIALIZING");

        try {
            await loadMetadata();
            await loadSignature();
            await loadPage(0);
        } catch (error) {
            setStatus("ERROR");
            elements.data.replaceChildren();

            const message = document.createElement("div");
            message.className = "rv-message";
            message.textContent =
                error.message || "Unable to initialize viewer.";

            elements.data.appendChild(message);
        }
    }

    initialize();
})();