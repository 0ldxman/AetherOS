// Эфир: приёмник на одной частоте. Слышно то, что пришло после выхода на частоту; опрос раз в 2 секунды.
(function () {
    "use strict";
    const { el, csrf, notice } = window.apps;
    const root = document.getElementById("air");
    const urls = root.dataset;
    const state = JSON.parse(document.getElementById("air-state").textContent);
    const readout = document.getElementById("air-freq");
    const log = document.getElementById("air-log");
    const scanner = document.getElementById("air-scanner");
    const found = document.getElementById("air-found");
    const text = document.getElementById("air-text");
    const callButton = document.getElementById("air-call");
    const mode = document.getElementById("air-mode");
    const STEP = 0.005;
    let last = 0;
    let timer = null;

    async function call(url, body) {
        const response = await fetch(url, body === undefined ? { credentials: "same-origin" } : {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || "no response");
        return data;
    }

    function status(textLine) { document.getElementById("air-status").textContent = textLine; }

    function show() {
        readout.value = state.freq;
        callButton.textContent = state.callsign || "listener";
        callButton.disabled = !state.can_tx;
        const form = document.getElementById("air-tx");
        form.setAttribute("aria-disabled", state.can_tx ? "false" : "true");
        text.disabled = !state.can_tx;
        text.placeholder = state.can_tx ? "" : "sign in to transmit";
        document.getElementById("air-since").textContent = "rx since " + new Date(state.since).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    }

    function line(row) {
        const node = el("div", "line" + (row.station ? " station" : "") + (row.mine ? " mine" : "") + (row.hidden ? " noise" : ""));
        node.append(el("span", "at", row.at), el("span", "who", row.callsign), el("span", "text", row.text));
        const flag = el("button", "flag", "report");
        flag.type = "button";
        flag.title = "report this transmission";
        flag.hidden = row.mine || row.station || row.hidden || !state.can_tx;
        flag.addEventListener("click", async () => {
            try { await call(urls.reportUrl, { id: row.id, reason: "" }); flag.remove(); notice("report sent"); } catch (error) { notice(error.message); }
        });
        node.append(flag);
        return node;
    }

    function clear() {
        last = 0;
        log.replaceChildren(el("p", "quiet", "listening on " + state.freq + " MHz…"));
    }

    async function poll() {
        try {
            const data = await call(urls.listenUrl + "?after=" + last);
            if (data.freq !== state.freq) return;
            if (data.rows.length) {
                log.querySelector(".quiet")?.remove();
                const near = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
                data.rows.forEach((row) => log.append(line(row)));
                last = data.rows[data.rows.length - 1].id;
                if (near) log.scrollTop = log.scrollHeight;
            }
            status("");
        } catch (error) {
            status("signal lost: " + error.message);
        }
    }

    async function tune(value) {
        try {
            const data = await call(urls.tuneUrl, { freq: value });
            Object.assign(state, data);
            clear();
            show();
            poll();
        } catch (error) {
            notice(error.message);
            readout.value = state.freq;
        }
    }

    function stepBy(direction) {
        const next = (Math.round(parseFloat(state.freq) / STEP) + direction) * STEP;
        tune(next.toFixed(3));
    }

    readout.addEventListener("keydown", (event) => {
        if (event.key === "Enter") { event.preventDefault(); tune(readout.value); }
        else if (event.key === "ArrowUp") { event.preventDefault(); stepBy(1); }
        else if (event.key === "ArrowDown") { event.preventDefault(); stepBy(-1); }
        else if (event.key === "Escape") { readout.value = state.freq; readout.blur(); }
    });
    readout.addEventListener("blur", () => { if (readout.value.trim() !== state.freq) tune(readout.value); });
    root.querySelectorAll(".step").forEach((button) => button.addEventListener("click", () => stepBy(Number(button.dataset.step))));

    document.getElementById("air-tx").addEventListener("submit", async (event) => {
        event.preventDefault();
        const value = text.value.trim();
        if (!value || !state.can_tx) return;
        mode.textContent = "TX";
        mode.classList.add("tx");
        try { await call(urls.txUrl, { text: value }); text.value = ""; await poll(); } catch (error) { notice(error.message); }
        setTimeout(() => { mode.textContent = "RX"; mode.classList.remove("tx"); }, 400);
    });

    // скан: участок до 0.5 МГц, список частот с активностью; щелчок выводит на частоту
    function openScanner(open) {
        scanner.hidden = !open;
        log.hidden = open;
        if (open) {
            const base = parseFloat(state.freq);
            document.getElementById("air-low").value = Math.max(3, base - 0.25).toFixed(3);
            document.getElementById("air-high").value = Math.min(30, base + 0.25).toFixed(3);
            found.replaceChildren();
        }
    }
    document.getElementById("air-scan").addEventListener("click", () => openScanner(scanner.hidden));
    document.getElementById("air-scan-close").addEventListener("click", () => openScanner(false));
    document.getElementById("air-scan-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const low = document.getElementById("air-low").value;
        const high = document.getElementById("air-high").value;
        found.replaceChildren(el("li", "quiet", "sweeping…"));
        try {
            const data = await call(urls.scanUrl + "?low=" + encodeURIComponent(low) + "&high=" + encodeURIComponent(high));
            found.replaceChildren(...(data.rows.length ? data.rows.map((row) => {
                const item = el("li");
                const button = el("button");
                button.type = "button";
                button.append(el("span", "", row.freq), el("span", "", row.count + " tx · " + (row.ago ? row.ago + " min ago" : "just now")));
                button.addEventListener("click", () => { openScanner(false); tune(row.freq); });
                item.append(button);
                return item;
            }) : [el("li", "quiet", "no activity in " + low + "–" + high)]));
        } catch (error) {
            found.replaceChildren(el("li", "quiet", error.message));
        }
    });

    // позывной меняется на месте: щелчок превращает его в поле, Enter сохраняет, Esc отменяет
    callButton.addEventListener("click", () => {
        const input = el("input", "field callinput");
        input.value = state.callsign;
        input.maxLength = 12;
        input.setAttribute("aria-label", "new callsign (once a week)");
        input.title = "2-12 letters, digits or '-'; can be changed once a week";
        callButton.replaceWith(input);
        input.focus();
        input.select();
        const done = () => { input.replaceWith(callButton); show(); };
        input.addEventListener("keydown", async (event) => {
            if (event.key === "Escape") return done();
            if (event.key !== "Enter") return;
            const name = input.value.trim();
            if (name && name.toUpperCase() !== state.callsign) {
                try { state.callsign = (await call(urls.callsignUrl, { name })).callsign; notice("callsign: " + state.callsign); } catch (error) { notice(error.message); }
            }
            done();
        });
        input.addEventListener("blur", done);
    });

    show();
    clear();
    poll();
    timer = setInterval(poll, 2000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
})();
