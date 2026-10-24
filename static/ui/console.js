/* ==================================================
   AETHER / CONSOLE
   Проигрыватель консольных сцен: список шагов, который собирает
   Python (console/scene.py), здесь превращается в анимацию вывода.
   Один и тот же проигрыватель нужен экрану входа, терминалу и
   переходам между машинами.

       const term = Aether.console.create(container, { flashTarget, onChoice });
       const result = await term.play(scene, { vars: { code: "HTTP 500" } });
       // result.choice: id варианта, если в сцене был выбор

   Стили лежат в static/ui/console.css, подключать вместе.
   ================================================== */

(function () {
    "use strict";

    const Aether = (window.Aether = window.Aether || {});

    const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const NOISE = "#%&/\\?01<>=+*".split("");

    class Abort extends Error {}

    const randomInt = (min, max) => Math.floor(min + Math.random() * (max - min + 1));
    const pick = list => list[randomInt(0, list.length - 1)];

    function el(tag, className) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        return node;
    }

    function fill(value, vars) {
        if (!vars) return String(value);
        return String(value).replace(/\{(\w+)\}/g, (match, key) => (key in vars ? vars[key] : match));
    }

    function create(container, options) {
        options = options || {};

        let current = null;          // строка, в которую дописываем
        let cursor = null;
        let skipping = REDUCED;      // пропуск анимации: любая клавиша или клик
        let playing = 0;
        const ids = {};              // id -> элемент, для glitch
        const keyHandlers = new Set();


        /* ---------- время ---------- */

        // обычная пауза: при пропуске заканчивается сразу
        function wait(ms, run) {
            if (run.aborted) return Promise.reject(new Abort());
            if (skipping || ms <= 0) return Promise.resolve();
            return new Promise((resolve, reject) => {
                setTimeout(() => (run.aborted ? reject(new Abort()) : resolve()), ms);
            });
        }

        // настоящая пауза: пропуск её не сокращает (задержки сюжетных событий)
        function realWait(ms, run) {
            if (run.aborted) return Promise.reject(new Abort());
            return new Promise((resolve, reject) => {
                setTimeout(() => (run.aborted ? reject(new Abort()) : resolve()), ms);
            });
        }

        const delayOf = value => (Array.isArray(value) ? randomInt(value[0], value[1]) : value || 0);


        /* ---------- строки и курсор ---------- */

        function hideCursor() {
            if (cursor) {
                cursor.remove();
                cursor = null;
            }
        }

        function newLine() {
            hideCursor();
            current = el("div", "con-line");
            container.appendChild(current);
            scrollDown();
            return current;
        }

        function ensureLine() {
            return current || newLine();
        }

        // курсор в конце строки или внутри parent (например, внутри варианта выбора)
        function showCursor(parent) {
            hideCursor();
            cursor = el("span", "con-cursor");
            (parent || ensureLine()).appendChild(cursor);
        }

        function span(style) {
            const node = el("span", style ? "con-" + style : "");
            ensureLine().appendChild(node);
            return node;
        }

        function scrollDown() {
            container.scrollTop = container.scrollHeight;
        }


        /* ---------- печать ---------- */

        // human: неровный ритм, пауза в раздумье и (typo) одна опечатка, которую замечают и стирают
        async function typeInto(target, value, opts, run, cursorParent) {
            const human = Boolean(opts.human);
            const hesitateAt = human ? randomInt(2, Math.max(3, value.length - 3)) : -1;
            const typoAt = human && opts.typo && value.length > 10 ? randomInt(4, value.length - 4) : -1;

            for (let i = 0; i < value.length; i++) {
                if (skipping) {
                    target.textContent = value;
                    break;
                }

                if (i === hesitateAt) {
                    showCursor(cursorParent);
                    await wait(randomInt(350, 700), run);
                }

                if (i === typoAt && /[a-z]/.test(value[i])) {
                    const wrong = pick("abcdefghijklmnopqrstuvwxyz".replace(value[i], "").split(""));
                    target.textContent += wrong;
                    showCursor(cursorParent);
                    await wait(randomInt(420, 760), run);
                    target.textContent = target.textContent.slice(0, -1);
                    await wait(130, run);
                }

                target.textContent += value[i];
                showCursor(cursorParent);
                await wait(
                    human ? randomInt(45, 130) + (value[i] === " " ? randomInt(30, 120) : 0) : opts.speed || 22,
                    run
                );
            }

            showCursor(cursorParent);
        }

        // стирание по буквам, как будто человек нажал Backspace
        async function eraseFrom(target, run, cursorParent) {
            while (target.textContent.length) {
                target.textContent = target.textContent.slice(0, -1);
                showCursor(cursorParent);
                await wait(24, run);
            }
        }

        // Текст «портится» и становится другим. Прыгают только отличающиеся буквы:
        // у aether-main и aether-null общее «aether-» остаётся на месте.
        async function glitchTo(target, to, frames, run) {
            const from = target.textContent;

            if (skipping) {
                target.textContent = to;
                return;
            }

            const length = Math.max(from.length, to.length);
            const start = frames * 0.35;
            const step = frames * 0.045;

            target.classList.add("con-warning");

            for (let frame = 0; frame < frames; frame++) {
                let shown = "";

                for (let i = 0; i < length; i++) {
                    const wanted = to[i] || "";
                    const settled = frame > start + i * step;

                    shown += wanted === (from[i] || "") || settled ? wanted : pick(NOISE);
                }

                target.textContent = shown;
                await wait(55, run);
            }

            target.textContent = to;
            target.classList.remove("con-warning");
        }


        /* ---------- шаги ---------- */

        const OPS = {
            async text(op, run, vars) {
                const node = span(op.style);
                node.textContent = fill(op.value, vars);
                if (op.id) ids[op.id] = node;
                showCursor();
            },

            async newline() {
                hideCursor();
                if (!current) newLine();
                current = null;
            },

            async type(op, run, vars) {
                const node = span(op.style);
                await typeInto(node, fill(op.value, vars), op, run);
            },

            async dots(op, run, vars) {
                const label = span();
                label.textContent = fill(op.label, vars);

                const dots = span("dim");
                const count = op.count || 14;

                for (let i = 0; i < count; i++) {
                    dots.textContent += ".";
                    showCursor();
                    await wait((op.ms || 500) / count, run);
                }

                const result = span(op.style);
                result.textContent = " " + fill(op.status, vars);
                showCursor();
                await wait(70, run);
            },

            async progress(op, run, vars) {
                const label = span();
                label.textContent = fill(op.label, vars);

                const bar = span("dim");
                const width = op.width || 24;
                const steps = 25;

                for (let i = 0; i <= steps; i++) {
                    const percent = Math.round((i * 100) / steps);
                    const filled = Math.round((width * percent) / 100);

                    bar.textContent = `[${"#".repeat(filled)}${"-".repeat(width - filled)}] ${String(percent).padStart(3)}%`;
                    showCursor();
                    await wait((op.ms || 1200) / steps, run);
                }

                await wait(70, run);
            },

            async pause(op, run) {
                const jitter = op.jitter ? randomInt(-op.jitter, op.jitter) : 0;
                await wait(Math.max(0, (op.ms || 0) + jitter), run);
            },

            async clear() {
                container.replaceChildren();
                current = null;
                cursor = null;
                Object.keys(ids).forEach(key => delete ids[key]);
            },

            async flash(op, run) {
                if (skipping) return;

                const target = options.flashTarget || container;

                for (let i = 0; i < 2; i++) {
                    target.classList.add("con-flash");
                    await wait(70, run);
                    target.classList.remove("con-flash");
                    await wait(70, run);
                }
            },

            async glitch(op, run, vars) {
                const target = ids[op.id];
                if (target) await glitchTo(target, fill(op.to, vars), op.frames || 14, run);
            },

            async one_of(op, run, vars, result) {
                await runSteps(pick(op.scenes), run, vars, result);
            },

            choice: choiceOp
        };

        async function runSteps(steps, run, vars, result) {
            for (const step of steps) {
                if (run.aborted) throw new Abort();

                const handler = OPS[step.op];

                if (!handler) {
                    console.warn("console: неизвестный шаг", step.op);
                    continue;
                }

                await handler(step, run, vars, result);
            }
        }


        /* ---------- выбор ---------- */

        function keyLabel(option) {
            return option.key.replace(/[\[\]\s]/g, "");
        }

        async function choiceOp(op, run, vars, result) {
            const items = op.options.filter(item => !item.late);   // варианты, готовые к выбору
            const later = op.options.filter(item => item.late);    // появятся сами, позже
            let box = null;
            let promptLine = null;
            let promptText = null;
            let settled = false;
            let focusedId = null;

            const child = { aborted: false };   // останавливает «поздние» варианты, когда ответ получен
            let resolveAnswer;
            const answered = new Promise(resolve => { resolveAnswer = resolve; });

            if (options.onChoice) options.onChoice();

            const buttons = () => Array.from(box.querySelectorAll(".con-option"));

            function answer(id) {
                if (settled) return;
                settled = true;
                child.aborted = true;
                keyHandlers.delete(onKey);

                buttons().forEach(button => {
                    button.disabled = true;
                    if (button.dataset.option === id) button.classList.add("con-chosen");
                });

                hideCursor();
                current = null;   // строка приглашения закрыта: следующая сцена начнёт с новой
                resolveAnswer(id);
            }

            function labelFor(item) {
                return fill(Array.isArray(item.label) ? pick(item.label) : item.label, vars);
            }

            // forming: текст варианта ещё печатается, подпись «[ ? ]» занимает место, но не видна
            function makeButton(item, forming) {
                const button = el("button", "con-option");
                button.type = "button";
                button.dataset.option = item.id;

                const main = el("span", "con-option-main");
                const keyEl = el("span", "con-option-key" + (forming ? " con-hidden" : ""));
                const labelEl = el("span", "con-option-label");

                keyEl.textContent = item.key + "  ";
                main.append(keyEl, labelEl);

                if (forming) {
                    button.disabled = true;
                } else {
                    labelEl.textContent = item.tag ? labelFor(item).padEnd(24) : labelFor(item);

                    if (item.style) main.classList.add("con-" + item.style);

                    if (item.tag) {
                        const tag = el("span", "con-option-tag");
                        tag.textContent = item.tag;
                        main.appendChild(tag);
                    }
                }

                button.appendChild(main);
                button.addEventListener("click", () => answer(item.id));
                button.addEventListener("focus", () => { focusedId = item.id; });

                return { button, main, keyEl, labelEl };
            }

            function refreshPrompt() {
                promptText.textContent = `${op.prompt || "Select"} [${items.map(keyLabel).join("/")}] `;
            }

            function onKey(event) {
                const hit = items.find(item => (item.keys || []).includes(event.key.toLowerCase()));

                if (hit) {
                    event.preventDefault();
                    answer(hit.id);
                    return true;
                }

                if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                    event.preventDefault();
                    const list = buttons().filter(button => !button.disabled);
                    const index = list.indexOf(document.activeElement);
                    const step = event.key === "ArrowDown" ? 1 : -1;
                    list[(index + step + list.length) % list.length].focus();
                    return true;
                }

                return false;
            }

            // Вариант появляется на месте: сначала его текст печатается простой строкой,
            // потом он «оформляется под кнопку» (подпись, цвет, мерцание).
            async function appear(item) {
                await realWait(delayOf(item.late.after_ms), child);

                skipping = REDUCED;   // этот кусок проигрывается по-настоящему
                const made = makeButton(item, true);
                box.appendChild(made.button);

                await typeInto(made.labelEl, labelFor(item), { human: true, typo: item.late.typo }, child, made.main);
                await wait(item.late.settle_ms || 450, child);

                made.button.classList.add("con-flicker");
                await wait(160, child);
                made.button.classList.remove("con-flicker");

                made.keyEl.classList.remove("con-hidden");
                if (item.style) made.main.classList.add("con-" + item.style);
                made.button.disabled = false;

                items.push(item);
                refreshPrompt();
                showCursor(promptLine);

                if (item.rewrites) await rewrite(item, made);
            }

            // Пока игрок не отвечает, текст стирается и набирается другой на том же месте
            async function rewrite(item, made) {
                const spec = item.rewrites;
                let shown = made.labelEl.textContent;

                for (;;) {
                    await realWait(delayOf(spec.after_ms), child);

                    skipping = REDUCED;
                    const next = pick(spec.labels.filter(label => label !== shown));

                    await eraseFrom(made.labelEl, child, made.main);
                    await wait(randomInt(300, 700), child);
                    await typeInto(made.labelEl, next, { human: true, typo: false }, child, made.main);

                    shown = next;
                    showCursor(promptLine);
                }
            }

            keyHandlers.add(onKey);

            box = el("div", "con-options");
            container.appendChild(box);
            items.forEach(item => box.appendChild(makeButton(item, false).button));

            promptLine = newLine();
            promptText = el("span");
            promptLine.appendChild(promptText);
            refreshPrompt();
            showCursor(promptLine);

            const first = buttons()[0];
            if (first) first.focus({ preventScroll: true });
            scrollDown();

            later.forEach(item => {
                appear(item).catch(error => {
                    if (!(error instanceof Abort)) console.error(error);
                });
            });

            const id = await answered;
            result.choice = id;
        }


        /* ---------- пропуск и запуск ---------- */

        document.addEventListener("keydown", event => {
            if (event.ctrlKey || event.altKey || event.metaKey) return;

            for (const handler of keyHandlers) {
                if (handler(event)) return;
            }

            if (playing) skipping = true;
        });

        document.addEventListener("pointerdown", () => {
            if (playing) skipping = true;
        });

        async function play(scene, opts) {
            opts = opts || {};

            const run = { aborted: false };
            const result = {};

            skipping = REDUCED;
            playing += 1;

            try {
                await runSteps(scene, run, opts.vars, result);
            } catch (error) {
                if (!(error instanceof Abort)) throw error;
            } finally {
                playing -= 1;
            }

            return result;
        }

        return { play, container };
    }

    Aether.console = { create };
})();
