/* ==================================================
   ЧЕРНОВИК РЕДАКТОРА ДОКУМЕНТА
   Редактор объекта раз в пару секунд откладывает текст в браузере
   (поля уже переименованы filesystem/item_admin.js: title, type, body, infobox).
   Если страницу закрыли без сохранения, при следующем открытии
   предлагает восстановить. Черновик, совпавший с тем, что уже
   сохранено, выбрасывается молча, так что после обычного сохранения
   ничего делать не нужно.
   ================================================== */

(function () {
    "use strict";

    const PREFIX = "aether-draft:";
    const KEY = PREFIX + location.pathname;
    const DELAY_MS = 1500;
    const MAX_AGE_MS = 30 * 24 * 3600 * 1000;
    const FIELDS = ["title", "type", "body", "infobox", "url"];

    const inputs = {};

    FIELDS.forEach(function (name) {
        inputs[name] = document.getElementById("id_" + name);
    });

    if (!inputs.body) {
        return;
    }

    /* ---------- Хранилище ---------- */

    function read(key) {
        try {
            return JSON.parse(localStorage.getItem(key) || "null");
        } catch (error) {
            return null;
        }
    }

    function write(key, value) {
        try {
            if (value === null) {
                localStorage.removeItem(key);
            } else {
                localStorage.setItem(key, JSON.stringify(value));
            }
        } catch (error) {
            // хранилище недоступно или переполнено: без черновиков редактор работает как раньше
        }
    }

    function dropStale() {
        try {
            Object.keys(localStorage).forEach(function (key) {
                if (key.indexOf(PREFIX) !== 0) {
                    return;
                }

                const draft = read(key);

                if (!draft || Date.now() - draft.savedAt > MAX_AGE_MS) {
                    write(key, null);
                }
            });
        } catch (error) {
            // см. write
        }
    }

    /* ---------- Состояние формы ---------- */

    function snapshot() {
        const values = {};

        FIELDS.forEach(function (name) {
            values[name] = inputs[name] ? inputs[name].value : "";
        });

        return values;
    }

    function same(a, b) {
        return FIELDS.every(function (name) {
            return a[name] === b[name];
        });
    }

    const baseField = document.querySelector('input[name="base_version"]');
    const base = baseField ? baseField.value : "";

    const initial = snapshot();

    /* ---------- Восстановление ---------- */

    function setValue(name, value) {
        const input = inputs[name];

        if (!input || input.value === value) {
            return;
        }

        const host = document.querySelector('.aether-editor[data-field="' + name + '"]');
        const editor = host && host._aetherEditor;

        if (editor) {
            // через редактор: тогда работает отмена и обновляется предпросмотр
            editor.view.dispatch({
                changes: { from: 0, to: editor.view.state.doc.length, insert: value },
            });
            return;
        }

        input.value = value;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function restore(draft) {
        FIELDS.forEach(function (name) {
            setValue(name, draft.values[name]);
        });
    }

    function offer(draft) {
        const form = document.querySelector(".wp-split__form") || document.body;
        const box = document.createElement("div");

        box.className = "wp-draft";
        box.setAttribute("role", "status");

        const when = new Date(draft.savedAt).toLocaleString("ru-RU");
        const changed = draft.base && base && draft.base !== base;

        const text = document.createElement("span");

        text.textContent =
            "Найден несохранённый черновик от " + when + "." +
            (changed ? " С тех пор объект изменили: восстановление заменит их правки." : "");

        function button(label, handler) {
            const el = document.createElement("button");

            el.type = "button";
            el.textContent = label;
            el.addEventListener("click", handler);

            return el;
        }

        box.append(
            text,
            button("Восстановить", function () {
                restore(draft);
                box.remove();
            }),
            button("Отбросить", function () {
                write(KEY, null);
                box.remove();
            })
        );

        form.insertBefore(box, form.firstChild);
    }

    /* ---------- Автосохранение ---------- */

    let timer = 0;

    function save() {
        const values = snapshot();

        if (same(values, initial)) {
            write(KEY, null);
            return;
        }

        write(KEY, { values: values, base: base, savedAt: Date.now() });
    }

    function schedule() {
        clearTimeout(timer);
        timer = setTimeout(save, DELAY_MS);
    }

    function start() {
        FIELDS.forEach(function (name) {
            const input = inputs[name];

            if (input) {
                input.addEventListener("input", schedule);
                input.addEventListener("change", schedule);
            }
        });

        window.addEventListener("pagehide", save);
    }

    dropStale();

    const draft = read(KEY);

    if (draft && draft.values) {
        // совпал с сохранённым: после обычного сохранения черновик не нужен
        if (same(draft.values, initial)) {
            write(KEY, null);
        } else {
            offer(draft);
        }
    }

    start();
})();
