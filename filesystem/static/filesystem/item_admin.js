/* Форма объекта в админке.
   1. Редактор вики ищет поля по id (title, type, body, infobox); у объекта они name, format, body, meta: переименовываем до его запуска.
   2. Поля содержимого (текст, ассет, ссылка, сцена, письмо) показываются по формату: что вводится, говорит реестр форматов. */
(function () {
    "use strict";

    const RENAME = {id_name: "id_title", id_format: "id_type", id_meta: "id_infobox"};
    Object.keys(RENAME).forEach(function (from) {
        const field = document.getElementById(from);
        if (!field) {
            return;
        }
        field.id = RENAME[from];
        document.querySelectorAll('label[for="' + from + '"]').forEach(function (label) {
            label.setAttribute("for", RENAME[from]);
        });
    });

    const table = JSON.parse((document.getElementById("item-formats") || {textContent: "{}"}).textContent || "{}");
    const ALLOWED = {
        text: ["body"],
        text_asset: ["body", "asset"],
        asset: ["asset"],
        link_asset: ["url", "asset"],
        scene: ["scene"],
        message: ["message"],
        none: [],
    };
    const FIELDS = ["body", "asset", "url", "scene", "message"];
    const format = document.getElementById("id_type");
    const split = document.getElementById("wp-split");

    function apply() {
        const known = table[format ? format.value : ""];
        const allowed = ALLOWED[known ? known.content : "text_asset"] || [];
        FIELDS.forEach(function (name) {
            const row = document.querySelector(".form-row.field-" + name);
            if (row) {
                row.hidden = allowed.indexOf(name) < 0;
            }
        });
        if (split) {
            split.dataset.page = known && known.markup ? "1" : "0";
        }
    }

    if (format) {
        format.addEventListener("change", apply);
        format.addEventListener("input", apply);
    }
    apply();
})();
