// Эфир: приёмник. Слышно то, что пришло после выхода на частоту; опрос раз в 2 секунды.
// Панорама сама обходит участок ±250 кГц вокруг частоты (сервер пускает обход не чаще раза в 10 секунд).
(function () {
    "use strict";
    const { el, csrf, notice } = window.apps;
    const root = document.getElementById("air");
    const urls = root.dataset;
    const state = JSON.parse(document.getElementById("air-state").textContent);
    const $ = (id) => document.getElementById(id);
    const vfo = $("air-vfo"), input = $("air-freq"), log = $("air-log"), text = $("air-text"), ptt = $("air-ptt");
    const callButton = $("air-call"), canvas = $("air-scope"), hover = $("air-hover"), mode = $("air-mode");
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // частоты считаем в килогерцах целыми, чтобы не копить ошибки округления
    const GRID = 5;
    const LOW = kHz(state.low), HIGH = kHz(state.high), WIDTH = kHz(state.scan_width);
    const SCAN_EVERY = 12000, POLL_EVERY = 2000;
    function kHz(value) { return Math.round(parseFloat(String(value).replace(",", ".")) * 1000); }
    function mhz(k) { return (k / 1000).toFixed(3); }
    function snap(k) { return Math.min(HIGH, Math.max(LOW, Math.round(k / GRID) * GRID)); }
    function clock(date) { return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }); }

    let shown = kHz(state.freq);     // что на шкале (при вращении колесом опережает настроенное)
    let last = 0;
    let tuneTimer = null;

    async function call(url, body) {
        const response = await fetch(url, body === undefined ? { credentials: "same-origin" } : {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) { const error = new Error(data.error || "no response"); error.status = response.status; throw error; }
        return data;
    }
    function status(line) { $("air-status").textContent = line; }

    // ---------- шкала частоты: каждая цифра крутится колесом в своём разряде ----------
    const PLACES = [10000, 1000, null, 100, 10, GRID];          // десятки МГц, МГц, точка, сотни, десятки, единицы кГц
    function drawVfo() {
        vfo.replaceChildren();
        [...mhz(shown).padStart(6, " ")].forEach((ch, i) => {
            if (ch === ".") { vfo.append(el("span", "dot", ".")); return; }
            const digit = el("span", "d" + (ch === " " ? " lead" : ""), ch === " " ? "0" : ch);
            digit.dataset.place = PLACES[i];
            vfo.append(digit);
        });
        vfo.setAttribute("aria-valuenow", mhz(shown));
        vfo.setAttribute("aria-valuetext", mhz(shown) + " MHz");
        drawRuler();
        markMemory();
    }
    function retune(k, now) {
        shown = snap(k);
        drawVfo();
        draw();
        clearTimeout(tuneTimer);
        tuneTimer = setTimeout(() => tune(mhz(shown)), now ? 0 : 350);
    }
    function stepK() { return Math.round(parseFloat($("air-step").value) * 1000); }
    vfo.addEventListener("wheel", (event) => {
        event.preventDefault();
        const place = Number(event.target.dataset?.place) || stepK();
        retune(shown + (event.deltaY < 0 ? place : -place));
    }, { passive: false });
    vfo.addEventListener("click", () => openInput(""));
    vfo.addEventListener("keydown", (event) => {
        const moves = { ArrowUp: stepK(), ArrowDown: -stepK(), ArrowRight: stepK(), ArrowLeft: -stepK(), PageUp: 100, PageDown: -100 };
        if (event.key in moves) { event.preventDefault(); retune(shown + moves[event.key]); }
        else if (event.key === "Enter") { event.preventDefault(); openInput(""); }
        else if (/^[0-9.,]$/.test(event.key)) { event.preventDefault(); openInput(event.key); }
    });
    function openInput(start) {
        input.value = start || mhz(shown);
        vfo.hidden = true;
        input.hidden = false;
        input.focus();
        if (!start) input.select();
    }
    function closeInput(apply) {
        if (input.hidden) return;
        input.hidden = true;
        vfo.hidden = false;
        if (apply && input.value.trim() && kHz(input.value) !== kHz(state.freq)) tune(input.value);
        vfo.focus();
    }
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") { event.preventDefault(); closeInput(true); }
        else if (event.key === "Escape") closeInput(false);
    });
    input.addEventListener("blur", () => closeInput(true));
    root.querySelectorAll(".air-arrow").forEach((button) =>
        button.addEventListener("click", () => retune(shown + Number(button.dataset.step) * stepK(), true)));
    // стрелки работают и без фокуса на шкале, если игрок не печатает
    document.addEventListener("keydown", (event) => {
        if (event.target.closest("input, select, textarea, button, [contenteditable]") || event.target === vfo) return;
        if (event.key === "ArrowUp" || event.key === "ArrowDown") { event.preventDefault(); retune(shown + (event.key === "ArrowUp" ? 1 : -1) * stepK()); }
    });

    // ---------- состояние ----------
    function show() {
        shown = kHz(state.freq);
        drawVfo();
        $("air-label").textContent = state.label || "open channel";
        $("air-freqtitle").textContent = state.freq + " MHz";
        callButton.textContent = state.callsign || "listener";
        callButton.disabled = !state.can_tx;
        const live = state.can_tx && !state.inhibit;
        ptt.disabled = !live;
        text.disabled = !live;
        $("air-prompt").textContent = (state.callsign || "listener") + "@" + state.freq + " ›";
        text.placeholder = !state.can_tx ? "receive only: sign in to transmit" : state.inhibit ? "transmit inhibited on this band" : "message, then Enter";
        text.setAttribute("aria-label", "transmission on " + state.freq + " MHz");
        $("air-since").textContent = clock(new Date(state.since));
        setMode(state.inhibit ? "RX · TX INHIBIT" : "RX");
    }
    function setMode(label, tx) {
        mode.textContent = label;
        mode.classList.toggle("tx", !!tx);
    }

    // ---------- журнал приёма ----------
    function row(item) {
        const node = el("div", "air-row" + (item.station ? " station" : "") + (item.mine ? " mine" : "") + (item.hidden ? " noise" : ""));
        node.append(el("span", "at", item.at), el("span", "who", item.callsign), el("span", "text", item.text));
        const flag = el("button", "flag", "REPORT");
        flag.type = "button";
        flag.title = "report this transmission to the operators";
        flag.hidden = item.mine || item.station || item.hidden || !state.can_tx;
        flag.addEventListener("click", async () => {
            try { await call(urls.reportUrl, { id: item.id, reason: "" }); flag.remove(); notice("report sent"); } catch (error) { notice(error.message); }
        });
        node.append(flag);
        return node;
    }
    function note(line) {
        log.append(el("p", "air-note", line));
        log.scrollTop = log.scrollHeight;
    }
    function started() { note("— tuned " + state.freq + " MHz at " + clock(new Date(state.since)) + ", listening —"); }

    async function poll() {
        try {
            const data = await call(urls.listenUrl + "?after=" + last);
            if (data.freq !== state.freq) return;
            if (data.rows.length) {
                const near = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
                data.rows.forEach((item) => {
                    log.append(row(item));
                    if (!item.mine) kick(item.station ? 11 : 6 + Math.random() * 3);
                });
                last = data.rows[data.rows.length - 1].id;
                if (near) log.scrollTop = log.scrollHeight;
            }
            status("");
        } catch (error) {
            status("signal lost: " + error.message);
        }
    }

    async function tune(value) {
        clearTimeout(tuneTimer);
        try {
            const data = await call(urls.tuneUrl, { freq: value });
            const moved = data.freq !== state.freq;
            Object.assign(state, data);
            show();
            if (moved) { last = 0; started(); sweep(); }
            poll();
        } catch (error) {
            notice(error.message);
            shown = kHz(state.freq);
            drawVfo();
            draw();
        }
    }

    // ---------- S-метр ----------
    let level = 1.5;
    function kick(value) { level = Math.max(level, value); }
    function meter() {
        const floor = calm ? 1.5 : 1.2 + Math.random() * 0.9;
        level = Math.max(floor, level - 0.18);
        const lit = Math.min(12, Math.round(level));
        const bars = $("air-bars");
        if (!bars.children.length) for (let i = 0; i < 12; i++) bars.append(el("i", i >= 9 ? "over" : ""));
        [...bars.children].forEach((bar, i) => bar.classList.toggle("lit", i < lit));
        $("air-s").textContent = lit <= 9 ? "S" + lit : "S9+" + (lit - 9) * 20;
    }

    // ---------- панорама ----------
    let found = [];
    let scannedAt = 0;
    let scanTimer = null;
    let hoverK = null;
    function view() {
        const low = Math.max(LOW, Math.min(HIGH - WIDTH, kHz(state.freq) - WIDTH / 2));
        return { low, high: low + WIDTH };
    }
    function gutter() { return parseFloat(getComputedStyle(root).getPropertyValue("--air-gutter")) || 22; }
    function share(k, range) { return (k - range.low) / (range.high - range.low); }

    function drawRuler() {
        const range = view();
        const ticks = $("air-ticks"), labels = $("air-labels");
        ticks.replaceChildren();
        labels.replaceChildren();
        for (let k = Math.ceil(range.low / 25) * 25; k <= range.high; k += 25) {
            const tick = el("i", k % 100 ? "minor" : "");
            tick.style.left = share(k, range) * 100 + "%";
            ticks.append(tick);
            if (k % 100 === 0) {
                const label = el("span", "", mhz(k));
                label.style.left = share(k, range) * 100 + "%";
                labels.append(label);
            }
        }
        $("air-thumb").style.left = share(shown, range) * 100 + "%";
    }

    const COLUMNS = WIDTH / GRID + 1;
    let noise = new Float32Array(COLUMNS);
    function shake() { for (let i = 0; i < COLUMNS; i++) noise[i] = noise[i] * 0.6 + (0.03 + Math.random() * Math.random() * 0.09) * 0.4; }
    function draw() {
        const ratio = window.devicePixelRatio || 1;
        const width = canvas.clientWidth, height = canvas.clientHeight;
        if (!width || !height) return;
        if (canvas.width !== Math.round(width * ratio)) { canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); }
        const ctx = canvas.getContext("2d");
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        ctx.clearRect(0, 0, width, height);
        const css = getComputedStyle(canvas);
        const light = css.color, muted = getComputedStyle(root).getPropertyValue("--font-muted").trim() || light;
        const accent = getComputedStyle(root).getPropertyValue("--accent").trim() || light;
        const range = view();
        const pad = gutter(), usable = width - pad * 2, column = usable / (COLUMNS - 1), bar = Math.max(1, Math.min(3, column * 0.6));
        const base = height - 6;
        const heat = new Map(found.map((item) => [item.k, item]));
        // сетка: еле заметные горизонтали
        ctx.globalAlpha = 0.12;
        ctx.fillStyle = light;
        for (let y = base; y > 6; y -= (base - 6) / 4) ctx.fillRect(pad, Math.round(y), usable, 1);
        for (let i = 0; i < COLUMNS; i++) {
            const k = range.low + i * GRID;
            const x = Math.round(pad + i * column - bar / 2);
            const hit = heat.get(k);
            let value = noise[i];
            if (k === kHz(state.freq)) value = Math.max(value, (level - 1) / 12 * 0.9);
            ctx.fillStyle = muted;
            ctx.globalAlpha = 0.55;
            ctx.fillRect(x, base - value * (base - 8), bar, value * (base - 8));
            if (hit) {
                const peak = Math.min(0.92, 0.28 + Math.log2(1 + hit.count) * 0.17);
                ctx.fillStyle = light;
                ctx.globalAlpha = Math.max(0.35, 1 - hit.ago / 15);
                ctx.fillRect(x, base - peak * (base - 8), bar, peak * (base - 8));
            }
        }
        // курсор настроенной частоты и наведённая частота
        ctx.globalAlpha = 1;
        ctx.fillStyle = accent;
        ctx.fillRect(Math.round(pad + share(shown, range) * usable), 0, 1, height);
        if (hoverK !== null) {
            ctx.globalAlpha = 0.5;
            ctx.fillStyle = light;
            ctx.fillRect(Math.round(pad + share(hoverK, range) * usable), 0, 1, height);
        }
        ctx.globalAlpha = 1;
    }

    async function sweep() {
        clearTimeout(scanTimer);
        const wait = scannedAt + 10500 - Date.now();
        if (wait > 0) { scanTimer = setTimeout(sweep, wait); return; }
        const range = view();
        $("air-sweep").textContent = "SCOPE / SWEEPING";
        try {
            const data = await call(urls.scanUrl + "?low=" + mhz(range.low) + "&high=" + mhz(range.high));
            found = data.rows.map((item) => ({ k: kHz(item.freq), count: item.count, ago: item.ago }));
            scannedAt = Date.now();
            $("air-sweep").textContent = "SCOPE ±" + WIDTH / 2 + " KHZ · 15 MIN · " + clock(new Date());
            draw();
        } catch (error) {
            scannedAt = Date.now();
            if (error.status === 429) { scanTimer = setTimeout(sweep, 10500); return; }
            $("air-sweep").textContent = "SCOPE / NO DATA";
        }
        scanTimer = setTimeout(sweep, SCAN_EVERY);
    }

    // курсор мыши: точка под мышью, а рядом со всплеском — сам всплеск
    function freqAt(event) {
        const box = canvas.getBoundingClientRect();
        const range = view();
        const k = snap(range.low + ((event.clientX - box.left - gutter()) / (box.width - 2 * gutter())) * WIDTH);
        const close = found.reduce((best, item) => (Math.abs(item.k - k) <= 10 && (!best || Math.abs(item.k - k) < Math.abs(best.k - k)) ? item : best), null);
        return close ? close.k : k;
    }
    canvas.addEventListener("mousemove", (event) => {
        hoverK = freqAt(event);
        const hit = found.find((item) => item.k === hoverK);
        hover.hidden = false;
        hover.textContent = mhz(hoverK) + (hit ? " · " + hit.count + " tx · " + (hit.ago ? hit.ago + " min ago" : "now") : "");
        const box = canvas.getBoundingClientRect();
        hover.style.left = Math.min(box.width - 60, Math.max(60, event.clientX - box.left)) + "px";
        draw();
    });
    canvas.addEventListener("mouseleave", () => { hover.hidden = true; hoverK = null; draw(); });
    canvas.addEventListener("click", (event) => retune(freqAt(event), true));

    // ---------- память: M1–M3 и вызывной канал ----------
    const MEM_KEY = "air-memory";
    let memory = [null, null, null];
    try { const saved = JSON.parse(localStorage.getItem(MEM_KEY) || "null"); if (Array.isArray(saved)) memory = [0, 1, 2].map((i) => saved[i] || null); } catch (error) { /* без памяти браузера каналы живут до закрытия */ }
    function keep() { try { localStorage.setItem(MEM_KEY, JSON.stringify(memory)); } catch (error) { /* не сохранилось: не беда */ } }
    function memButton(label, value, onPick, onStore) {
        const button = el("button", value ? "" : "blank");
        button.type = "button";
        button.append(el("span", "air-key", label), document.createTextNode(value || "---.---"));
        button.dataset.freq = value || "";
        button.title = onStore ? (value ? "go to " + value + " · right click or hold: store current" : "store current frequency") : "calling channel";
        let held = null, stored = false;
        if (onStore) {
            const store = () => { stored = true; onStore(); };
            button.addEventListener("pointerdown", () => { stored = false; held = setTimeout(store, 600); });
            ["pointerup", "pointerleave"].forEach((name) => button.addEventListener(name, () => clearTimeout(held)));
            button.addEventListener("contextmenu", (event) => { event.preventDefault(); clearTimeout(held); store(); });
        }
        button.addEventListener("click", () => { if (!stored) onPick(); stored = false; });
        return button;
    }
    function drawMemory() {
        $("air-mem").replaceChildren(...memory.map((value, i) => memButton("M" + (i + 1), value,
            () => (value ? retune(kHz(value), true) : save(i)), () => save(i))),
            memButton("CALL", state.calling, () => retune(kHz(state.calling), true)));
        markMemory();
    }
    function save(i) {
        memory[i] = mhz(shown);
        keep();
        drawMemory();
        notice("M" + (i + 1) + " stored: " + memory[i] + " MHz");
    }
    function markMemory() {
        $("air-mem").querySelectorAll("button").forEach((button) => button.classList.toggle("cur", button.dataset.freq === mhz(shown)));
    }

    // ---------- передача ----------
    text.addEventListener("input", () => {
        const count = $("air-count");
        count.textContent = text.value.length + "/280";
        count.classList.toggle("near", text.value.length > 250);
    });
    $("air-tx").addEventListener("submit", async (event) => {
        event.preventDefault();
        const value = text.value.trim();
        if (!value || ptt.disabled) return;
        setMode("TX · ON AIR", true);
        ptt.classList.add("keyed");
        try {
            await call(urls.txUrl, { text: value });
            text.value = "";
            text.dispatchEvent(new Event("input"));
            await poll();
        } catch (error) { notice(error.message); }
        setTimeout(() => { setMode(state.inhibit ? "RX · TX INHIBIT" : "RX"); ptt.classList.remove("keyed"); }, 450);
    });

    // ---------- позывной: щелчок превращает его в поле, Enter сохраняет, Esc отменяет ----------
    callButton.addEventListener("click", () => {
        const field = el("input", "air-callinput");
        field.value = state.callsign;
        field.maxLength = 12;
        field.setAttribute("aria-label", "new callsign (once a week)");
        field.title = "2-12 letters, digits or '-'; can be changed once a week";
        callButton.replaceWith(field);
        field.focus();
        field.select();
        let closed = false;
        const done = () => { if (closed) return; closed = true; field.replaceWith(callButton); show(); };
        field.addEventListener("keydown", async (event) => {
            if (event.key === "Escape") return done();
            if (event.key !== "Enter") return;
            const name = field.value.trim();
            if (name && name.toUpperCase() !== state.callsign) {
                try { state.callsign = (await call(urls.callsignUrl, { name })).callsign; notice("callsign: " + state.callsign); } catch (error) { notice(error.message); }
            }
            done();
        });
        field.addEventListener("blur", done);
    });

    show();
    drawMemory();
    started();
    shake();
    draw();
    sweep();
    poll();
    setInterval(poll, POLL_EVERY);
    setInterval(() => { meter(); if (!calm) shake(); draw(); }, calm ? 600 : 160);
    window.addEventListener("resize", draw);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
})();
