/* ==================================================
   AETHER / CONDITION FIELDS
   Превращает textarea с data-condition-editor (secure/admin_widgets.py)
   в визуальный редактор условий. Список ключей лежит в data-keys.
   ================================================== */

(function () {
    "use strict";

    function setup(root) {
        if (!window.AetherConditionEditor) {
            return;
        }

        root.querySelectorAll("textarea[data-condition-editor]").forEach(function (field) {
            // шаблон новой строки inline'а ("__prefix__") оживёт, когда строку добавят
            if (field.id.indexOf("__prefix__") !== -1) {
                return;
            }

            let keys = [];

            try {
                keys = JSON.parse(field.dataset.keys || "[]");
            } catch (error) {
                console.error("Не удалось прочитать список ключей:", error);
            }

            window.AetherConditionEditor.create(field, {
                title: field.dataset.label,
                keys: keys,
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        setup(document);
    });

    // строка, добавленная в inline кнопкой «Add another»
    document.addEventListener("formset:added", function (event) {
        setup(event.target);
    });
})();
