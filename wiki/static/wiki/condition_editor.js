/* ==================================================
   Aether Wiki — Condition Editor
   ================================================== */

(function () {
    "use strict";


    /* ==================================================
       Helpers
       ================================================== */

    function isKey(value) {
        return (
            typeof value === "string" &&
            value.length > 0
        );
    }


    function isObject(value) {
        return (
            value !== null &&
            typeof value === "object" &&
            !Array.isArray(value)
        );
    }


    function isValidCondition(value) {
        if (isKey(value)) {
            return true;
        }

        if (!isObject(value)) {
            return false;
        }

        const keys = Object.keys(value);

        if (keys.length !== 1) {
            return false;
        }

        const operator = keys[0];

        if (operator === "all" || operator === "any") {
            if (
                !Array.isArray(value[operator]) ||
                value[operator].length === 0
            ) {
                return false;
            }

            return value[operator].every(
                isValidCondition
            );
        }

        if (operator === "not") {
            return isValidCondition(
                value.not
            );
        }

        return false;
    }


    function parseField(field) {
        const raw = field.value.trim();

        if (!raw) {
            return null;
        }

        try {
            const value = JSON.parse(raw);
            /*
            * Empty object means:
            * no restriction.
            */

            if (
                isObject(value) &&
                Object.keys(value).length === 0
            ) {
                return null;
            }

            if (!isValidCondition(value)) {
                return {
                    __invalid: true,
                    raw
                };
            }
            return value;

        } catch (error) {
            /*
             * A bare string is technically a valid
             * condition, but Django JSONField normally
             * stores strings as JSON strings.
             *
             * Therefore malformed JSON is considered
             * invalid instead of silently accepting it.
             */

            return {
                __invalid: true,
                raw
            };
        }
    }


    function serializeField(value) {
        if (value === null) {
            return "";
        }

        return JSON.stringify(value);
    }


    function createElement(
        tag,
        className = "",
        text = null
    ) {
        const element =
            document.createElement(tag);

        if (className) {
            element.className = className;
        }

        if (text !== null) {
            element.textContent = text;
        }

        return element;
    }


    /* ==================================================
       Condition Editor
       ================================================== */

    class ConditionEditor {

        constructor(field, options = {}) {
            this.field = field;

            this.options = {
                title:
                    options.title ||
                    field.dataset.label ||
                    field.name ||
                    "Condition",

                keys: Array.isArray(options.keys)
                    ? options.keys
                    : []
            };

            this.value =
                parseField(this.field);

            this.root = null;
            this.content = null;

            this.init();
        }


        /* ==============================================
           Init
           ============================================== */

        init() {
            this.field.classList.add(
                "aether-condition-source"
            );

            this.root = createElement(
                "div",
                "aether-condition-editor"
            );

            this.root.dataset.field =
                this.field.id || "";

            this.render();

            this.field.insertAdjacentElement(
                "afterend",
                this.root
            );
        }


        /* ==============================================
           Render
           ============================================== */

        render() {
            this.root.replaceChildren();

            const header =
                createElement(
                    "div",
                    "aether-condition-editor__header"
                );

            const title =
                createElement(
                    "div",
                    "aether-condition-editor__title",
                    this.options.title
                );

            header.appendChild(title);

            this.root.appendChild(header);

            this.content =
                createElement(
                    "div",
                    "aether-condition-editor__content"
                );

            this.root.appendChild(
                this.content
            );

            if (
                this.value &&
                this.value.__invalid
            ) {
                this.renderInvalid();

                return;
            }

            if (this.value === null) {
                this.renderEmpty();

                return;
            }

            this.content.appendChild(
                this.renderNode(
                    this.value,
                    []
                )
            );
        }


        renderEmpty() {
            const wrapper =
                createElement(
                    "div",
                    "aether-condition-empty"
                );

            const label =
                createElement(
                    "span",
                    "aether-condition-empty__label",
                    "No restriction"
                );

            const button =
                createElement(
                    "button",
                    "aether-condition-button",
                    "Add condition"
                );

            button.type = "button";

            button.addEventListener(
                "click",
                () => {
                    this.value =
                        this.createKey();

                    this.sync();
                    this.render();
                }
            );

            wrapper.appendChild(label);
            wrapper.appendChild(button);

            this.content.appendChild(
                wrapper
            );
        }


        renderInvalid() {
            const wrapper =
                createElement(
                    "div",
                    "aether-condition-invalid"
                );

            const heading =
                createElement(
                    "strong",
                    "",
                    "Invalid condition"
                );

            const description =
                createElement(
                    "span",
                    "",
                    "The existing value cannot be represented by this editor."
                );

            const raw =
                createElement(
                    "code",
                    "aether-condition-invalid__raw",
                    this.value.raw
                );

            const button =
                createElement(
                    "button",
                    "aether-condition-button",
                    "Replace with condition"
                );

            button.type = "button";

            button.addEventListener(
                "click",
                () => {
                    this.value =
                        this.createKey();

                    this.sync();
                    this.render();
                }
            );

            wrapper.appendChild(heading);
            wrapper.appendChild(description);
            wrapper.appendChild(raw);
            wrapper.appendChild(button);

            this.content.appendChild(
                wrapper
            );
        }


        /* ==============================================
           Recursive rendering
           ============================================== */

        renderNode(value, path) {
            if (isKey(value)) {
                return this.renderKey(
                    value,
                    path
                );
            }

            if (
                !isObject(value)
            ) {
                return createElement(
                    "div",
                    "aether-condition-invalid-node",
                    "Invalid condition"
                );
            }

            if ("all" in value) {
                return this.renderGroup(
                    "all",
                    value.all,
                    path
                );
            }

            if ("any" in value) {
                return this.renderGroup(
                    "any",
                    value.any,
                    path
                );
            }

            if ("not" in value) {
                return this.renderNot(
                    value.not,
                    path
                );
            }

            return createElement(
                "div",
                "aether-condition-invalid-node",
                "Invalid condition"
            );
        }


        /* ==============================================
           KEY node
           ============================================== */

        renderKey(value, path) {
            const node =
                createElement(
                    "div",
                    "aether-condition-node aether-condition-node--key"
                );

            const select =
                this.createKeySelect(
                    value,
                    path
                );

            node.appendChild(select);

            const controls =
                createElement(
                    "div",
                    "aether-condition-node__controls"
                );

            controls.appendChild(
                this.createNodeMenu(path)
            );

            controls.appendChild(
                this.createRemoveButton(path)
            );

            node.appendChild(
                controls
            );

            return node;
        }


        /* ==============================================
           ALL / ANY node
           ============================================== */

        renderGroup(
            operator,
            children,
            path
        ) {
            const node =
                createElement(
                    "div",
                    "aether-condition-node aether-condition-node--group"
                );

            const header =
                createElement(
                    "div",
                    "aether-condition-group__header"
                );

            const label =
                createElement(
                    "span",
                    "aether-condition-operator",
                    operator.toUpperCase()
                );

            header.appendChild(label);

            const controls =
                createElement(
                    "div",
                    "aether-condition-node__controls"
                );

            controls.appendChild(
                this.createAddMenu(path)
            );

            controls.appendChild(
                this.createNodeMenu(path)
            );

            controls.appendChild(
                this.createRemoveButton(path)
            );

            header.appendChild(
                controls
            );

            node.appendChild(header);

            const childrenContainer =
                createElement(
                    "div",
                    "aether-condition-group__children"
                );

            children.forEach(
                (child, index) => {
                    childrenContainer.appendChild(
                        this.renderNode(
                            child,
                            path.concat(index)
                        )
                    );
                }
            );

            node.appendChild(
                childrenContainer
            );

            return node;
        }


        /* ==============================================
           NOT node
           ============================================== */

        renderNot(
            child,
            path
        ) {
            const node =
                createElement(
                    "div",
                    "aether-condition-node aether-condition-node--not"
                );

            const header =
                createElement(
                    "div",
                    "aether-condition-group__header"
                );

            const label =
                createElement(
                    "span",
                    "aether-condition-operator",
                    "NOT"
                );

            header.appendChild(label);

            const controls =
                createElement(
                    "div",
                    "aether-condition-node__controls"
                );

            controls.appendChild(
                this.createNodeMenu(path)
            );

            controls.appendChild(
                this.createRemoveButton(path)
            );

            header.appendChild(
                controls
            );

            node.appendChild(header);

            const childrenContainer =
                createElement(
                    "div",
                    "aether-condition-group__children"
                );

            childrenContainer.appendChild(
                this.renderNode(
                    child,
                    path.concat("not")
                )
            );

            node.appendChild(
                childrenContainer
            );

            return node;
        }


        /* ==============================================
           Key selector
           ============================================== */

        createKeySelect(
            currentValue,
            path
        ) {
            const select =
                document.createElement("select");

            select.className =
                "aether-condition-key";

            const known =
                this.options.keys.some(
                    key =>
                        this.keySlug(key) ===
                        currentValue
                );

            if (!known) {
                const option =
                    document.createElement(
                        "option"
                    );

                option.value =
                    currentValue;

                option.textContent =
                    `${currentValue} (unknown)`;

                option.selected = true;

                select.appendChild(option);
            }

            this.options.keys.forEach(
                key => {
                    const slug =
                        this.keySlug(key);

                    if (!slug) {
                        return;
                    }

                    const option =
                        document.createElement(
                            "option"
                        );

                    option.value = slug;
                    option.textContent = slug;

                    if (
                        key.description
                    ) {
                        option.title =
                            key.description;
                    }

                    if (
                        slug === currentValue
                    ) {
                        option.selected = true;
                    }

                    select.appendChild(option);
                }
            );

            select.addEventListener(
                "change",
                () => {
                    this.setAtPath(
                        path,
                        select.value
                    );

                    this.sync();
                    this.render();
                }
            );

            return select;
        }


        keySlug(key) {
            if (
                typeof key === "string"
            ) {
                return key;
            }

            if (
                key &&
                typeof key === "object"
            ) {
                return key.slug || "";
            }

            return "";
        }


        /* ==============================================
           Menus
           ============================================== */

        createNodeMenu(path) {
            const wrapper =
                createElement(
                    "div",
                    "aether-condition-menu"
                );

            const button =
                createElement(
                    "button",
                    "aether-condition-icon-button",
                    "⋮"
                );

            button.type = "button";
            button.title =
                "Change condition";
            button.setAttribute(
                "aria-label",
                "Change condition"
            );

            const popup =
                createElement(
                    "div",
                    "aether-condition-menu__popup"
                );

            popup.hidden = true;

            const options = [
                [
                    "KEY",
                    () => {
                        this.setAtPath(
                            path,
                            this.createKey()
                        );
                    }
                ],
                [
                    "ALL",
                    () => {
                        this.setAtPath(
                            path,
                            this.createGroup(
                                "all"
                            )
                        );
                    }
                ],
                [
                    "ANY",
                    () => {
                        this.setAtPath(
                            path,
                            this.createGroup(
                                "any"
                            )
                        );
                    }
                ],
                [
                    "NOT",
                    () => {
                        this.setAtPath(
                            path,
                            {
                                not: this.createKey()
                            }
                        );
                    }
                ]
            ];

            options.forEach(
                ([label, callback]) => {
                    const item =
                        createElement(
                            "button",
                            "aether-condition-menu__item",
                            label
                        );

                    item.type = "button";

                    item.addEventListener(
                        "click",
                        () => {
                            popup.hidden = true;

                            callback();

                            this.sync();
                            this.render();
                        }
                    );

                    popup.appendChild(item);
                }
            );

            button.addEventListener(
                "click",
                event => {
                    event.stopPropagation();

                    popup.hidden =
                        !popup.hidden;
                }
            );

            document.addEventListener(
                "click",
                event => {
                    if (
                        !wrapper.contains(
                            event.target
                        )
                    ) {
                        popup.hidden = true;
                    }
                }
            );

            wrapper.appendChild(button);
            wrapper.appendChild(popup);

            return wrapper;
        }


        createAddMenu(path) {
            const wrapper =
                createElement(
                    "div",
                    "aether-condition-menu"
                );

            const button =
                createElement(
                    "button",
                    "aether-condition-small-button",
                    "+ Add"
                );

            button.type = "button";

            const popup =
                createElement(
                    "div",
                    "aether-condition-menu__popup"
                );

            popup.hidden = true;

            const options = [
                [
                    "KEY",
                    () => {
                        this.addToGroup(
                            path,
                            this.createKey()
                        );
                    }
                ],
                [
                    "ALL",
                    () => {
                        this.addToGroup(
                            path,
                            this.createGroup("all")
                        );
                    }
                ],
                [
                    "ANY",
                    () => {
                        this.addToGroup(
                            path,
                            this.createGroup("any")
                        );
                    }
                ],
                [
                    "NOT",
                    () => {
                        this.addToGroup(
                            path,
                            {
                                not: this.createKey()
                            }
                        );
                    }
                ]
            ];

            options.forEach(
                ([label, callback]) => {
                    const item =
                        createElement(
                            "button",
                            "aether-condition-menu__item",
                            label
                        );

                    item.type = "button";

                    item.addEventListener(
                        "click",
                        () => {
                            popup.hidden = true;

                            callback();

                            this.sync();
                            this.render();
                        }
                    );

                    popup.appendChild(item);
                }
            );

            button.addEventListener(
                "click",
                event => {
                    event.stopPropagation();

                    popup.hidden =
                        !popup.hidden;
                }
            );

            document.addEventListener(
                "click",
                event => {
                    if (
                        !wrapper.contains(
                            event.target
                        )
                    ) {
                        popup.hidden = true;
                    }
                }
            );

            wrapper.appendChild(button);
            wrapper.appendChild(popup);

            return wrapper;
        }


        createRemoveButton(path) {
            const button =
                createElement(
                    "button",
                    "aether-condition-icon-button",
                    "×"
                );

            button.type = "button";
            button.title =
                "Remove condition";
            button.setAttribute(
                "aria-label",
                "Remove condition"
            );

            button.addEventListener(
                "click",
                () => {
                    this.removeAtPath(path);

                    this.sync();
                    this.render();
                }
            );

            return button;
        }


        /* ==============================================
           Tree access
           ============================================== */

        getAtPath(path) {
            let current = this.value;

            for (const part of path) {
                if (
                    current === null ||
                    current === undefined
                ) {
                    return undefined;
                }

                if (
                    typeof part === "number"
                ) {
                    if (
                        !Array.isArray(current)
                    ) {
                        return undefined;
                    }

                    current =
                        current[part];

                    continue;
                }

                if (
                    part === "not"
                ) {
                    if (
                        !isObject(current) ||
                        !("not" in current)
                    ) {
                        return undefined;
                    }

                    current =
                        current.not;

                    continue;
                }

                return undefined;
            }

            return current;
        }


        setAtPath(path, value) {
            /*
             * Root node.
             */

            if (path.length === 0) {
                this.value = value;
                return;
            }

            const parentPath =
                path.slice(0, -1);

            const last =
                path[path.length - 1];

            const parent =
                this.getAtPath(parentPath);

            if (
                parent === null ||
                parent === undefined
            ) {
                return;
            }

            if (
                typeof last === "number" &&
                Array.isArray(parent)
            ) {
                parent[last] = value;
                return;
            }

            if (
                last === "not" &&
                isObject(parent)
            ) {
                parent.not = value;
            }
        }


        removeAtPath(path) {
            /*
             * Removing the root means:
             *
             *     no restriction
             */

            if (path.length === 0) {
                this.value = null;
                return;
            }

            const parentPath =
                path.slice(0, -1);

            const last =
                path[path.length - 1];

            const parent =
                this.getAtPath(parentPath);

            if (
                parent === null ||
                parent === undefined
            ) {
                return;
            }

            /*
             * Child inside ALL / ANY.
             */

            if (
                typeof last === "number" &&
                Array.isArray(parent)
            ) {
                parent.splice(last, 1);

                /*
                 * Backend does not allow empty
                 * all/any arrays.
                 *
                 * If the parent becomes empty,
                 * remove the entire group.
                 */

                if (
                    parent.length === 0
                ) {
                    this.removeAtPath(
                        parentPath.slice(0, -1)
                    );
                }

                return;
            }

            /*
             * NOT child.
             *
             * NOT must always contain exactly
             * one valid condition.
             *
             * Therefore removing its child
             * removes the NOT node itself.
             */

            if (
                last === "not" &&
                isObject(parent)
            ) {
                this.removeAtPath(
                    parentPath.slice(0, -1)
                );
            }
        }


        addToGroup(
            path,
            condition
        ) {
            const group =
                this.getAtPath(path);

            if (
                !isObject(group)
            ) {
                return;
            }

            if (
                Array.isArray(group.all)
            ) {
                group.all.push(condition);
                return;
            }

            if (
                Array.isArray(group.any)
            ) {
                group.any.push(condition);
                return;
            }

            /*
             * NOT cannot contain multiple children.
             *
             * Therefore no Add button is rendered
             * for NOT.
             */
        }


        /* ==============================================
           Factory helpers
           ============================================== */

        createKey() {
            const first =
                this.options.keys[0];

            const slug =
                this.keySlug(first);

            return slug || "";
        }


        createGroup(operator) {
            return {
                [operator]: [
                    this.createKey()
                ]
            };
        }


        /* ==============================================
           Synchronization
           ============================================== */

        sync() {
            const value = this.value;

            this.field.value =
                value === null
                    ? "{}"
                    : JSON.stringify(value);

            this.field.dispatchEvent(
                new Event("input", {
                    bubbles: true,
                })
            );

            this.field.dispatchEvent(
                new Event("change", {
                    bubbles: true,
                })
            );
        }
    }


    /* ==================================================
       Public API
       ================================================== */

    window.AetherConditionEditor = {

        create(field, options = {}) {
            if (!field) {
                return null;
            }

            /*
             * Avoid creating the editor twice.
             */

            if (
                field.__aetherConditionEditor
            ) {
                return field.__aetherConditionEditor;
            }

            const editor =
                new ConditionEditor(
                    field,
                    options
                );

            field.__aetherConditionEditor =
                editor;

            return editor;
        }

    };

})();