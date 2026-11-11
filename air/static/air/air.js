// Эфир: передняя панель трансивера. Слышно то, что пришло после выхода на частоту; опрос раз в 2 секунды.
// Панорама сама обходит участок ±250 кГц вокруг частоты (сервер пускает обход не чаще раза в 10 секунд).
(function () {
    "use strict";
    const { el, csrf, notice } = window.apps;
    const root = document.getElementById("air");
    const urls = root.dataset;
    const state = JSON.parse(document.getElementById("air-state").textContent);
    const $ = (id) => document.getElementById(id);
    const vfo = $("air-vfo"), input = $("air-freq"), log = $("air-log"), text = $("air-text"), ptt = $("air-ptt");
    const callButton = $("air-call"), scope = $("air-scope"), peaks = $("air-peaks"), cursor = $("air-cursor"), hover = $("air-hover");
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // частоты считаем в килогерцах целыми, чтобы не копить ошибки округления
    const GRID = 5;
    const LOW = kHz(state.low), HIGH = kHz(state.high), WIDTH = kHz(state.scan_width);
    const SCAN_EVERY = 12000, POLL_EVERY = 2000;
    function kHz(value) { return Math.round(parseFloat(value) * 1000); }
    function mhz(k) { return (k / 1000).toFixed(3); }
    function snap(k) { return Math.min(HIGH, Math.max(LOW, Math.round(k / GRID) * GRID)); }

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
    function clock(date) { return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }); }

    // ---------- шкала частоты: каждая цифра крутится колесом в своём разряде ----------
    const PLACES = [10000, 1000, null, 100, 10, GRID];          // десятки МГц, МГц, точка, сотни, десятки, единицы кГц
    function drawVfo() {
        const textFreq = mhz(shown).padStart(6, " ");
        vfo.replaceChildren();
        [...textFreq].forEach((ch, i) => {
            if (ch === ".") { vfo.append(el("span", "dot", ".")); return; }
            const digit = el("span", "d" + (ch === " " ? " lead" : ""), ch === " " ? "0" : ch);
            digit.dataset.place = PLACES[i];
            vfo.append(digit);
        });
        vfo.append(el("span", "d small lead", ".00"));
        vfo.setAttribute("aria-valuenow", mhz(shown));
        vfo.setAttribute("aria-valuetext", mhz(shown) + " MHz");
        cursorAt();
        markMemory();
    }
    function retune(k, now) {
        shown = snap(k);
        drawVfo();
        clearTimeout(tuneTimer);
        tuneTimer = setTimeout(() => tune(mhz(shown)), now ? 0 : 350);
    }
    vfo.addEventListener("wheel", (event) => {
        event.preventDefault();
        const place = Number(event.target.dataset?.place) || stepK();
        retune(shown + (event.deltaY < 0 ? place : -place));
    }, { passive: false });
    vfo.addEventListener("click", () => openInput(""));
    vfo.addEventListener("keydown", (event) => {
        const moves = { ArrowUp: stepK(), ArrowDown: -stepK(), PageUp: 100, PageDown: -100 };
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
        if (apply && input.value.trim() && kHz(input.value.replace(",", ".")) !== kHz(state.freq)) tune(input.value);
        vfo.focus();
    }
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") { event.preventDefault(); closeInput(true); }
        else if (event.key === "Escape") closeInput(false);
    });
    input.addEventListener("blur", () => closeInput(true));

    function stepK() { return Math.round(parseFloat($("air-step").value) * 1000); }
    root.querySelectorAll(".key[data-step]").forEach((button) =>
        button.addEventListener("click", () => retune(shown + Number(button.dataset.step) * stepK(), true)));

    // ---------- состояние панели ----------
    function show() {
        shown = kHz(state.freq);
        drawVfo();
        $("air-label").textContent = state.label || "";
        $("air-inhibit").hidden = !state.inhibit;
        callButton.textContent = state.callsign || "— listener —";
        callButton.disabled = !state.can_tx;
        const live = state.can_tx && !state.inhibit;
        ptt.disabled = !live;
        text.disabled = !live;
        $("air-tx").setAttribute("aria-disabled", live ? "false" : "true");
        text.placeholder = !state.can_tx ? "receive only: sign in to transmit" : state.inhibit ? "transmit inhibited on this band" : "type, then PTT or Enter";
        $("air-txlamp").classList.toggle("off", !live);
        $("air-since").textContent = "rx since " + clock(new Date(state.since));
    }

    // ---------- приём: окно декодера ----------
    function line(row, fresh) {
        const node = el("div", "line" + (row.station ? " station" : "") + (row.mine ? " mine" : "") + (row.hidden ? " noise" : "") + (fresh ? " fresh" : ""));
        node.append(el("span", "at", row.at), el("span", "who", row.callsign), el("span", "text", row.text));
        const flag = el("button", "flag", "report");
        flag.type = "button";
        flag.title = "report this transmission to the operators";
        flag.hidden = row.mine || row.station || row.hidden || !state.can_tx;
        flag.addEventListener("click", async () => {
            try { await call(urls.reportUrl, { id: row.id, reason: "" }); flag.remove(); notice("report sent"); } catch (error) { notice(error.message); }
        });
        node.append(flag);
        return node;
    }
    function mark(textLine, cls) {
        log.append(el("p", "mark " + (cls || ""), textLine));
        log.scrollTop = log.scrollHeight;
    }

    async function poll(first) {
        try {
            const data = await call(urls.listenUrl + "?after=" + last);
            if (data.freq !== state.freq) return;
            if (data.rows.length) {
                log.querySelector(".mark.wait")?.remove();
                const near = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
                data.rows.forEach((row) => {
                    log.append(line(row, !first));
                    if (!row.mine) kick(row.station ? 11 : 6 + Math.random() * 3);
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
            if (moved || !log.children.length) {
                last = 0;
                mark("tuned " + state.freq + " MHz · " + clock(new Date(state.since)), "tune");
                mark("listening…", "wait");
                rescope();
            }
            poll(true);
        } catch (error) {
            notice(error.message);
            shown = kHz(state.freq);
            drawVfo();
        }
    }

    // ---------- S-метр: шум и всплески принятых передач ----------
    const SEGMENTS = 12;
    const bars = $("air-bars");
    for (let i = 0; i < SEGMENTS; i++) {
        const bar = el("i", i >= 9 ? "hot-slot" : "");
        bar.style.height = (35 + i * 6) + "%";
        bars.append(bar);
    }
    let level = 1.5;
    function kick(value) { level = Math.max(level, value); }
    function meter() {
        const floor = calm ? 1.5 : 1.2 + Math.random() * 0.9;
        level = Math.max(floor, level - 0.18);
        const lit = Math.round(level);
        [...bars.children].forEach((bar, i) => {
            bar.classList.toggle("lit", i < lit);
            bar.classList.toggle("hot", i < lit && i >= 9);
        });
        $("air-s").textContent = lit <= 9 ? "S" + lit : "+" + (lit - 9) * 20;
    }
    setInterval(meter, 120);

    // ---------- панорама ----------
    let found = [];
    let scannedAt = 0;
    let scanTimer = null;
    function windowAround(k) {
        const low = Math.max(LOW, Math.min(HIGH - WIDTH, k - WIDTH / 2));
        return { low, high: low + WIDTH };
    }
    function share(k, view) { return ((k - view.low) / (view.high - view.low)) * 100; }
    function cursorAt() {
        const view = windowAround(kHz(state.freq));
        cursor.style.left = share(shown, view) + "%";
    }
    function drawScale(view) {
        const scale = $("air-scale");
        scale.replaceChildren();
        for (let k = Math.ceil(view.low / 100) * 100; k <= view.high; k += 100) {
            const tick = el("span", "", mhz(k));
            tick.style.left = share(k, view) + "%";
            scale.append(tick);
        }
    }
    function drawPeaks() {
        const view = windowAround(kHz(state.freq));
        drawScale(view);
        peaks.replaceChildren(...found.filter((row) => row.k >= view.low && row.k <= view.high).map((row) => {
            const peak = el("div", "peak" + (row.k === kHz(state.freq) ? " here" : ""));
            peak.style.left = share(row.k, view) + "%";
            peak.style.height = Math.min(92, 28 + Math.log2(1 + row.count) * 18) + "%";
            peak.style.opacity = Math.max(0.35, 1 - row.ago / 15);
            peak.title = mhz(row.k) + " · " + row.count + " tx · " + (row.ago ? row.ago + " min ago" : "just now");
            return peak;
        }));
        cursorAt();
    }
    async function sweep() {
        clearTimeout(scanTimer);
        const wait = scannedAt + 10500 - Date.now();
        if (wait > 0) { scanTimer = setTimeout(sweep, wait); return; }
        const view = windowAround(kHz(state.freq));
        try {
            const data = await call(urls.scanUrl + "?low=" + mhz(view.low) + "&high=" + mhz(view.high));
            found = data.rows.map((row) => ({ k: kHz(row.freq), count: row.count, ago: row.ago }));
            scannedAt = Date.now();
            $("air-sweep").textContent = "scope ±" + WIDTH / 2 + " kHz · " + clock(new Date());
            drawPeaks();
        } catch (error) {
            if (error.status === 429) { scannedAt = Date.now(); scanTimer = setTimeout(sweep, 10500); return; }
        }
        scanTimer = setTimeout(sweep, SCAN_EVERY);
    }
    function rescope() { drawPeaks(); sweep(); }

    function freqAt(event) {
        const box = scope.getBoundingClientRect();
        const view = windowAround(kHz(state.freq));
        return snap(view.low + ((event.clientX - box.left) / box.width) * (view.high - view.low));
    }
    scope.addEventListener("mousemove", (event) => {
        hover.hidden = false;
        hover.textContent = mhz(freqAt(event));
        hover.style.left = ((event.clientX - scope.getBoundingClientRect().left) / scope.clientWidth) * 100 + "%";
    });
    scope.addEventListener("mouseleave", () => { hover.hidden = true; });
    scope.addEventListener("click", (event) => {
        // щелчок рядом со всплеском ловит его точно
        const k = freqAt(event);
        const close = found.reduce((best, row) => (Math.abs(row.k - k) <= 6 && (!best || Math.abs(row.k - k) < Math.abs(best.k - k)) ? row : best), null);
        retune(close ? close.k : k, true);
    });

    // ---------- память: M1–M3 и вызывной канал ----------
    const MEM_KEY = "air-memory";
    let memory = [null, null, null];
    try { const saved = JSON.parse(localStorage.getItem(MEM_KEY) || "null"); if (Array.isArray(saved)) memory = [0, 1, 2].map((i) => saved[i] || null); } catch (error) { /* без памяти браузера каналы живут до закрытия */ }
    function keep() { try { localStorage.setItem(MEM_KEY, JSON.stringify(memory)); } catch (error) { /* не сохранилось: не беда */ } }
    function memKey(label, value, onPick, onStore) {
        const button = el("button", "key" + (value ? " set" : " empty"));
        button.type = "button";
        button.append(el("b", "", label), document.createTextNode(value || "———"));
        button.dataset.freq = value || "";
        button.title = onStore ? (value ? "click: go to " + value + " · hold: store current" : "click: store current frequency") : "calling channel";
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
        const box = $("air-mem");
        box.replaceChildren(...memory.map((value, i) => memKey("M" + (i + 1), value,
            () => (value ? retune(kHz(value), true) : save(i)), () => save(i))),
            memKey("CALL", state.calling, () => retune(kHz(state.calling), true)));
        markMemory();
    }
    function save(i) {
        memory[i] = mhz(shown);
        keep();
        drawMemory();
        const button = $("air-mem").children[i];
        button.classList.add("saved");
        setTimeout(() => button.classList.remove("saved"), 700);
        notice("M" + (i + 1) + " ← " + memory[i]);
    }
    function markMemory() {
        $("air-mem")?.querySelectorAll(".key").forEach((button) => button.classList.toggle("cur", button.dataset.freq === mhz(shown)));
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
        const lamp = $("air-txlamp"), rx = $("air-rx");
        lamp.classList.add("on"); rx.classList.remove("on"); ptt.classList.add("keyed");
        try {
            await call(urls.txUrl, { text: value });
            text.value = "";
            text.dispatchEvent(new Event("input"));
            await poll();
        } catch (error) { notice(error.message); }
        setTimeout(() => { lamp.classList.remove("on"); rx.classList.add("on"); ptt.classList.remove("keyed"); }, 450);
    });

    // ---------- позывной: щелчок превращает его в поле, Enter сохраняет, Esc отменяет ----------
    callButton.addEventListener("click", () => {
        const field = el("input", "field callinput");
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
    mark("tuned " + state.freq + " MHz · " + clock(new Date(state.since)), "tune");
    mark("listening…", "wait");
    rescope();
    poll(true);
    setInterval(poll, POLL_EVERY);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
})();
