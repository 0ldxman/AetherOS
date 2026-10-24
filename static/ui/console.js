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

        function showCursor() {
            hideCursor();
            cursor = el("span", "con-cursor");
            ensureLine().appendChild(cursor);
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
        async function typeInto(target, value, opts, run) {
            const human = Boolean(opts.human);
            const hesitateAt = human ? randomInt(2, Math.max(3, value.length - 3)) : -1;
            const typoAt = human && opts.typo && value.length > 10 ? randomInt(4, value.length - 4) : -1;

            for (let i = 0; i < value.length; i++) {
                if (skipping) {
                    target.textContent = value;
                    break;
                }

                if (i === hesitateAt) {
                    showCursor();
                    await wait(randomInt(350, 700), run);
                }

                if (i === typoAt && /[a-z]/.test(value[i])) {
                    const wrong = pick("abcdefghijklmnopqrstuvwxyz".replace(value[i], "").split(""));
                    target.textContent += wrong;
                    showCursor();
                    await wait(randomInt(420, 760), run);
                    target.textContent = target.textContent.slice(0, -1);
                    await wait(130, run);
                }

                target.textContent += value[i];
                showCursor();
                await wait(
                    human ? randomInt(45, 130) + (value[i] === " " ? randomInt(30, 120) : 0) : opts.speed || 22,
                    run
                );
            }

            showCursor();
        }

        // текст «портится» и становится другим: меняющиеся символы сначала прыгают, потом встают на место
        async function glitchTo(target, to, run) {
            const from = target.textContent;

            if (skipping) {
                target.textContent = to;
                return;
            }

            const length = Math.max(from.length, to.length);

            for (let frame = 0; frame < 14; frame++) {
                let shown = "";

                for (let i = 0; i < length; i++) {
                    const wanted = to[i] || "";
                    const settled = frame > 5 + i * 0.6;

                    shown += wanted === (from[i] || "") || settled ? wanted : pick(NOISE);
                }

                target.textContent = shown;
                await wait(55, run);
            }

            target.textContent = to;
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
                if (target) await glitchTo(target, fill(op.to, vars), run);
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
            let items = op.options.slice();
            let box = null;
            let prompt = null;
            let settled = false;
            let focusedId = null;

            const child = { aborted: false };   // отменяет события, когда ответ получен
            let resolveAnswer;
            const answered = new Promise(resolve => { resolveAnswer = resolve; });

            if (options.onChoice) options.onChoice();

            function buttons() {
                return Array.from(box.querySelectorAll(".con-option"));
            }

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

            function optionButton(item) {
                const button = el("button", "con-option");
                button.type = "button";
                button.dataset.option = item.id;

                const label = Array.isArray(item.label) ? pick(item.label) : item.label;
                const main = el("span", "con-option-main" + (item.style ? " con-" + item.style : ""));
                main.textContent = item.tag
                    ? `${item.key}  ${fill(label, vars).padEnd(24)}`
                    : `${item.key}  ${fill(label, vars)}`;

                if (item.tag) {
                    const tag = el("span", "con-option-tag");
                    tag.textContent = item.tag;
                    main.appendChild(tag);
                }

                button.appendChild(main);
                button.addEventListener("click", () => answer(item.id));
                button.addEventListener("focus", () => { focusedId = item.id; });
                return button;
            }

            // Список вариантов выводится заново, старый остаётся выше приглушённым:
            // консоль только дописывает, а не переписывает уже показанное.
            function render() {
                if (box) {
                    box.classList.add("con-stale");
                    buttons().forEach(button => { button.disabled = true; });
                }

                if (prompt) prompt.remove();
                hideCursor();
                current = null;

                box = el("div", "con-options");
                container.appendChild(box);
                items.forEach(item => box.appendChild(optionButton(item)));

                const keys = items.map(keyLabel).join("/");
                prompt = newLine();
                const text = el("span");
                text.textContent = `${op.prompt || "Select"} [${keys}] `;
                prompt.appendChild(text);
                showCursor();

                const target = buttons().find(button => button.dataset.option === focusedId) || buttons()[0];
                if (target) target.focus({ preventScroll: true });
                scrollDown();
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
                    const list = buttons();
                    const index = list.indexOf(document.activeElement);
                    const step = event.key === "ArrowDown" ? 1 : -1;
                    list[(index + step + list.length) % list.length].focus();
                    return true;
                }

                return false;
            }

            keyHandlers.add(onKey);
            render();

            // события: сюжетные куски, которые случаются, пока игрок выбирает
            (async () => {
                try {
                    for (const event of op.events || []) {
                        await realWait(delayOf(event.after_ms), child);

                        skipping = REDUCED;   // новый кусок проигрывается по-настоящему
                        if (box) {
                            box.classList.add("con-stale");
                            buttons().forEach(button => { button.disabled = true; });
                        }
                        if (prompt) prompt.remove();
                        prompt = null;
                        hideCursor();
                        current = null;

                        await runSteps(event.steps || [], child, vars, result);

                        items = items.concat(event.options || []);
                        render();
                    }
                } catch (error) {
                    if (!(error instanceof Abort)) console.error(error);
                }
            })();

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
