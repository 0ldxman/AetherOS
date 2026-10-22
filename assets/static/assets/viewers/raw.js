
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
    const filename = root.dataset.rawFilename || "";

    const PAGE_SIZE = 256;
    const SCAN_CHUNK_SIZE = 64 * 1024;
    const MAX_PATTERN_LENGTH = 4096;
    const MAX_MATCHES = 10000;
    const MAX_STRINGS = 5000;
    const MIN_STRING_LENGTH = 4;
    const MAX_DISPLAY_STRING_LENGTH = 2048;
    const MIN_PANEL_WIDTH = 180;
    const SPLITTER_WIDTH = 6;

    const elements = {
        tag: root.querySelector("[data-raw-tag]"),
        status: root.querySelector("[data-raw-status]"),
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

        strings: [],
        totalStrings: 0,
        stringsTruncated: false,

        view: "hex"
    };

    let hexRatio = 0.62;
    let resizing = false;
    let activePointerId = null;
    let operationId = 0;

    const signatures = [
        {
            bytes: [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A],
            name: "PNG image"
        },
        {
            bytes: [0x25, 0x50, 0x44, 0x46, 0x2D],
            name: "PDF document"
        },
        {
            bytes: [0x50, 0x4B, 0x03, 0x04],
            name: "ZIP archive / DOCX"
        },
        {
            bytes: [0x50, 0x4B, 0x05, 0x06],
            name: "ZIP archive (empty)"
        },
        {
            bytes: [0x4D, 0x5A],
            name: "DOS / Windows executable"
        },
        {
            bytes: [0xFF, 0xD8, 0xFF],
            name: "JPEG image"
        },
        {
            bytes: [0x47, 0x49, 0x46, 0x38],
            name: "GIF image"
        },
        {
            bytes: [0x1F, 0x8B],
            name: "GZIP archive"
        },
        {
            bytes: [0x53, 0x51, 0x4C, 0x69, 0x74, 0x65],
            name: "SQLite database"
        },
        {
            bytes: [0x52, 0x61, 0x72, 0x21, 0x1A, 0x07],
            name: "RAR archive"
        }
    ];

    /* =====================================================
       Basic helpers
       ===================================================== */

    function setStatus(message) {
        elements.status.textContent = message;
    }

    function formatSize(size) {
        if (size < 1024) {
            return size + " B";
        }

        if (size < 1024 * 1024) {
            return (size / 1024).toFixed(2) + " KB";
        }

        if (size < 1024 * 1024 * 1024) {
            return (size / (1024 * 1024)).toFixed(2) + " MB";
        }

        return (size / (1024 * 1024 * 1024)).toFixed(2) + " GB";
    }

    function formatOffset(offset) {
        return offset.toString(16).toUpperCase().padStart(8, "0");
    }

    function printable(byte) {
        return byte >= 0x20 && byte <= 0x7E;
    }

    function detectSignature(bytes) {
        for (const signature of signatures) {
            if (
                signature.bytes.every(
                    (byte, index) => bytes[index] === byte
                )
            ) {
                return signature.name;
            }
        }

        if (bytes.length === 0) {
            return "Empty file";
        }

        return "Unknown / no signature match";
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

        const bytes = await fetchRange(
            0,
            Math.min(15, state.size - 1)
        );

        elements.signature.textContent = detectSignature(bytes);
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

    function render() {
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

                hex.appendChild(
                    makeByte(byte, absoluteOffset, "rv-byte", matchBytes)
                );

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
    }

    async function loadPage(requestedOffset) {
        if (state.loading) {
            return;
        }

        const thisOperation = ++operationId;
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

            if (thisOperation !== operationId) {
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

            render();
            setStatus("READY");
        } catch (error) {
            if (thisOperation !== operationId) {
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
            if (thisOperation === operationId) {
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

    function parseHexPattern(value) {
        const cleaned = value.trim().replace(/^0x/i, "");

        if (!cleaned || !/^[0-9a-f\s,:-]+$/i.test(cleaned)) {
            return null;
        }

        const tokens = cleaned.split(/[\s,:-]+/).filter(Boolean);

        if (
            !tokens.length ||
            tokens.some(token => !/^[0-9a-f]{1,2}$/i.test(token))
        ) {
            return null;
        }

        return new Uint8Array(
            tokens.map(token => Number.parseInt(token, 16))
        );
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
            elements.searchCount.textContent = state.scanning
                ? "SCANNING..."
                : "NO MATCHES";
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

        const thisOperation = ++operationId;

        state.scanning = true;
        state.matches = [];
        state.totalMatches = 0;
        state.matchLength = pattern.length;
        state.searchPattern = pattern;
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
                () => thisOperation !== operationId
            );

            if (!completed || thisOperation !== operationId) {
                return;
            }

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
                renderStrings();
                render();
                setStatus("NO MATCHES");
            }
        } catch (error) {
            if (thisOperation !== operationId) {
                return;
            }

            setStatus("SEARCH ERROR");
            elements.searchCount.textContent =
                error.message || "Unable to search file.";
        } finally {
            if (thisOperation === operationId) {
                state.scanning = false;
                updateSearchControls();

                if (state.matches.length) {
                    setStatus("SEARCH COMPLETE");
                }
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

    function getStringSearchPattern() {
        if (!state.searchPattern || state.searchPattern.length === 0) {
            return null;
        }

        const bytes = state.searchPattern;

        // Highlight the query in the string list when it has a
        // printable ASCII representation.
        if ([...bytes].every(byte => byte >= 0x20 && byte <= 0x7E)) {
            return String.fromCharCode(...bytes);
        }

        // For text searches, the query may contain UTF-8 bytes.
        if (elements.searchMode.value === "text") {
            return elements.searchInput.value || null;
        }

        return null;
    }

    function appendHighlightedText(container, value, pattern) {
        if (!pattern) {
            container.textContent = value;
            return;
        }

        const lowerValue = value.toLocaleLowerCase();
        const lowerPattern = pattern.toLocaleLowerCase();

        if (!lowerPattern) {
            container.textContent = value;
            return;
        }

        let cursor = 0;

        while (cursor < value.length) {
            const index = lowerValue.indexOf(lowerPattern, cursor);

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

        const thisOperation = ++operationId;

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

        let runStart = 0;
        let runBytes = [];

        function finishRun() {
            if (runBytes.length === 0) {
                return;
            }

            const bytes = new Uint8Array(runBytes);

            const value = new TextDecoder("utf-8", {
                fatal: false
            }).decode(bytes);

            const cleaned = value.replace(/\uFFFD/g, "");

            if ([...cleaned].length >= MIN_STRING_LENGTH) {
                state.totalStrings++;

                if (state.strings.length < MAX_STRINGS) {
                    state.strings.push({
                        offset: runStart,
                        value: cleaned.slice(0, MAX_DISPLAY_STRING_LENGTH)
                    });
                } else {
                    state.stringsTruncated = true;
                }
            }

            runBytes = [];
        }

        try {
            const completed = await scanFile(
                async (bytes, chunkStart) => {
                    for (let i = 0; i < bytes.length; i++) {
                        const byte = bytes[i];
                        const offset = chunkStart + i;

                        const isAsciiPrintable =
                            byte >= 0x20 && byte <= 0x7E;

                        // Keep possible UTF-8 continuation and leading bytes.
                        const isUtf8Byte = byte >= 0x80 && byte <= 0xF4;

                        if (isAsciiPrintable || isUtf8Byte) {
                            if (runBytes.length === 0) {
                                runStart = offset;
                            }

                            runBytes.push(byte);
                        } else {
                            finishRun();
                        }
                    }
                },
                () => thisOperation !== operationId
            );

            if (!completed || thisOperation !== operationId) {
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
            if (thisOperation !== operationId) {
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
            if (thisOperation === operationId) {
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

        if (state.strings.length) {
            renderStrings();
        }
    });

    elements.searchInput.addEventListener("input", function () {
        if (state.strings.length) {
            renderStrings();
        }
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
        if (state.loading || state.scanning) {
            return;
        }

        ++operationId;

        state.start = 0;
        state.selected = null;
        state.bytes = new Uint8Array(0);

        state.matches = [];
        state.totalMatches = 0;
        state.matchLength = 0;
        state.searchPattern = new Uint8Array(0);
        state.currentMatch = -1;

        state.strings = [];
        state.totalStrings = 0;
        state.stringsTruncated = false;
        state.view = "hex";

        setStringsVisible(false);

        elements.data.replaceChildren();
        elements.searchCount.textContent = "NO SEARCH";
        elements.stringsCount.textContent = "—";

        elements.searchPrev.disabled = true;
        elements.searchNext.disabled = true;

        const extensionMatch = filename.match(/\.([^.\/\\]+)$/);
        const extension = extensionMatch
            ? extensionMatch[1].toUpperCase()
            : "BIN";

        elements.tag.textContent = `[RAW.${extension}]`;
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
