/*
 * ==================================================
 * AETHER WIKI EDITOR
 * ==================================================
 *
 * CodeMirror 6 + Aether Markup syntax highlighting.
 *
 * Архитектура:
 *
 *   CodeMirror
 *       ↓
 *   hidden Django textarea
 *       ↓
 *   server preview
 *
 * Preview остаётся полностью серверным.
 */

import {
  EditorState,
} from "https://esm.sh/@codemirror/state@6";

import {
  EditorView,
  keymap,
  drawSelection,
  lineNumbers,
  highlightActiveLine,
  highlightActiveLineGutter,
} from "https://esm.sh/@codemirror/view@6";

import {
  defaultKeymap,
  history,
  historyKeymap,
} from "https://esm.sh/@codemirror/commands@6";

import {
  syntaxHighlighting,
} from "https://esm.sh/@codemirror/language@6";


/*
 * Aether language layer.
 */

import {
  aetherLanguage,
} from "./editor/aether-language.js";


/*
 * Aether folding.
 */

import {
  aetherFoldService,
  aetherFoldGutter,
} from "./editor/aether-fold.js";


/*
 * Aether visual syntax theme.
 */

import {
  aetherHighlightStyle,
} from "./editor/aether-theme.js";

import "./condition_editor.js";

(function () {
  "use strict";


  /* ==================================================
   * ROOT
   * ================================================== */

  const root =
    document.getElementById("wp-split");

  if (!root) {
    return;
  }


  /* ==================================================
   * DOM
   * ================================================== */

  const previewUrl =
    root.dataset.previewUrl;

  const DELAY_MS = 400;

  const STORE =
    "aether-wiki-preview";

  const SPLIT_STORE =
    "aether-wiki-editor-split";

  const SPLIT_MIN_LEFT =
    320;

  const SPLIT_MIN_RIGHT =
    360;

  const SPLIT_DIVIDER =
    8;

  const SPLIT_BREAKPOINT =
    1100;


  const $ = (id) =>
    document.getElementById(id);


  const fields = {
    title: $("id_title"),
    type: $("id_type"),
    body: $("id_body"),
    infobox: $("id_infobox"),
  };


  const frames = {
    body: $("wp-frame-body"),
    infobox: $("wp-frame-infobox"),
  };


  const tabs =
    Array.from(
      root.querySelectorAll(".wp-tab")
    );


  const asSelect =
    $("wp-as");

  const keysBox =
    $("wp-keys");

  const statusEl =
    $("wp-status");


  const formPane =
    root.querySelector(
      ".wp-split__form"
    );


  const previewPane =
    root.querySelector(
      ".wp-pane"
    );


  /*
   * Все основные элементы должны существовать.
   */

  if (
    !formPane ||
    !previewPane ||
    !asSelect ||
    !keysBox ||
    !statusEl
  ) {
    return;
  }


  /* ==================================================
   * PREVIEW VIEWPORT
   * ================================================== */

  /*
   * В текущем HTML iframe находятся непосредственно
   * внутри .wp-pane.
   *
   * Создаём viewport динамически и переносим iframe
   * внутрь него.
   */

  const previewViewport =
    document.createElement("div");

  previewViewport.className =
    "wp-preview-viewport";


  /*
   * Явно задаём параметры viewport.
   *
   * CSS также содержит эти правила, но здесь они
   * задаются как дополнительная гарантия того,
   * что viewport корректно работает даже если
   * порядок CSS изменится.
   */

  previewViewport.style.flex =
    "1 1 auto";

  previewViewport.style.width =
    "100%";

  previewViewport.style.minWidth =
    "0";

  previewViewport.style.minHeight =
    "0";

  previewViewport.style.overflowX =
    "auto";

  previewViewport.style.overflowY =
    "hidden";

  previewViewport.style.position =
    "relative";

  previewViewport.style.boxSizing =
    "border-box";


  /*
   * Сохраняем текущие iframe.
   */

  Object.values(frames).forEach(
    (frame) => {

      if (!frame) {
        return;
      }


      /*
       * Теперь iframe находится внутри viewport,
       * поэтому старый flex: 1 от .wp-pane больше
       * не определяет его высоту.
       */

      frame.style.height =
        "100%";

      frame.style.minHeight =
        "100%";

      frame.style.minWidth =
        "100%";


      previewViewport.appendChild(
        frame
      );

    }
  );


  /*
   * Добавляем viewport после панели ключей.
   */

  previewPane.appendChild(
    previewViewport
  );


  /* ==================================================
   * SPLIT RESIZER
   * ================================================== */

  const splitResizer =
    document.createElement("div");

  splitResizer.className =
    "wp-resizer";

  splitResizer.setAttribute(
    "role",
    "separator"
  );

  splitResizer.setAttribute(
    "aria-orientation",
    "vertical"
  );

  splitResizer.setAttribute(
    "aria-label",
    "Изменить ширину редактора и предпросмотра"
  );


  /*
   * Вставляем divider между editor
   * и preview.
   */

  root.insertBefore(
    splitResizer,
    previewPane
  );


  /* ==================================================
   * HELPERS
   * ================================================== */

  const val = (el) =>
    el ? el.value : "";


  function csrf() {

    const input =
      document.querySelector(
        'input[name="csrfmiddlewaretoken"]'
      );

    return input
      ? input.value
      : "";
  }


  function keyBoxes() {

    return Array.from(
      keysBox.querySelectorAll(
        'input[type="checkbox"]'
      )
    );

  }


  /* ==================================================
   * EDITORS
   * ================================================== */

  const editors = {};


  /* ==================================================
   * EDITOR THEME
   * ================================================== */

  const aetherEditorTheme =
    EditorView.theme({

      "&": {
        height: "100%",
      },


      ".cm-scroller": {
        fontFamily:
          "var(--font-mono, 'JetBrains Mono', monospace)",

        lineHeight: "1.55",

        overflow: "auto",
      },


      ".cm-content": {
        padding: "14px 0",

        minHeight: "100%",
      },


      ".cm-line": {
        padding:
          "0 16px 0 8px",
      },


      ".cm-gutters": {
        fontFamily:
          "var(--font-mono, 'JetBrains Mono', monospace)",

        userSelect: "none",
      },


      ".cm-activeLineGutter": {
        background:
          "transparent",
      },


      ".cm-activeLine": {
        background:
          "rgba(255,255,255,.025)",
      },


      ".cm-cursor": {
        borderLeftWidth: "2px",
      },


      ".cm-selectionBackground": {
        backgroundColor:
          "rgba(63,208,255,.18) !important",
      },

    });


  /* ==================================================
   * TAB KEYMAP
   * ================================================== */

  /*
   * Tab вставляет четыре пробела.
   */

  const aetherTabKeymap =
    keymap.of([
      {
        key: "Tab",

        run: (view) => {

          view.dispatch(
            view.state.replaceSelection("    ")
          );

          return true;

        },
      },
    ]);


  /* ==================================================
   * EDITOR FACTORY
   * ================================================== */

  function createEditor(
    field,
    container,
    name
  ) {

    if (!field || !container) {
      return null;
    }


    /*
     * Не создаём CodeMirror повторно.
     */

    if (container._aetherEditor) {
      return container._aetherEditor;
    }


    /*
     * Сохраняем исходное значение
     * Django textarea.
     */

    const initialValue =
      field.value || "";


    /*
     * Скрываем оригинальное Django поле,
     * но НЕ удаляем его.
     *
     * Django продолжает использовать textarea
     * при submit.
     */

    field.classList.add(
      "aether-original-field"
    );


    /*
     * Контейнер CodeMirror.
     */

    const editorHost =
      document.createElement("div");

    editorHost.className =
      "aether-cm";


    container.appendChild(
      editorHost
    );


    /*
     * CodeMirror → Django textarea.
     */

    function syncField(value) {

      if (field.value === value) {
        return;
      }


      field.value = value;


      /*
       * Существующая логика preview
       * слушает обычные DOM events.
       */

      field.dispatchEvent(
        new Event("input", {
          bubbles: true,
        })
      );


      field.dispatchEvent(
        new Event("change", {
          bubbles: true,
        })
      );

    }


    /* ==================================================
     * CODEMIRROR EXTENSIONS
     * ================================================== */

    const extensions = [

      /*
       * Номера строк.
       */

      lineNumbers(),


      /*
       * Undo / redo.
       */

      history(),


      /*
       * Выделение текста.
       */

      drawSelection(),


      /*
       * Подсветка текущей строки.
       */

      highlightActiveLine(),

      highlightActiveLineGutter(),


      /*
       * ================================================
       * AETHER LANGUAGE
       * ================================================
       */

      aetherLanguage,

      aetherFoldService,

      aetherFoldGutter,


      /*
       * ================================================
       * AETHER SYNTAX HIGHLIGHTING
       * ================================================
       */

      syntaxHighlighting(
        aetherHighlightStyle
      ),


      /*
       * ================================================
       * EDITOR UI THEME
       * ================================================
       */

      aetherEditorTheme,


      /*
       * ================================================
       * TAB
       * ================================================
       */

      aetherTabKeymap,


      /*
       * ================================================
       * KEYMAP
       * ================================================
       */

      keymap.of([
        ...defaultKeymap,
        ...historyKeymap,
      ]),


      /*
       * ================================================
       * DOCUMENT CHANGES
       * ================================================
       */

      EditorView.updateListener.of(
        (update) => {

          if (!update.docChanged) {
            return;
          }


          syncField(
            update.state.doc.toString()
          );

        }
      ),

    ];


    /* ==================================================
     * EDITOR STATE
     * ================================================== */

    const state =
      EditorState.create({
        doc: initialValue,
        extensions,
      });


    /* ==================================================
     * EDITOR VIEW
     * ================================================== */

    const view =
      new EditorView({
        state,
        parent: editorHost,
      });


    /* ==================================================
     * EDITOR OBJECT
     * ================================================== */

    const editor = {
      view,
      host: editorHost,
      field,
      container,
    };


    container._aetherEditor =
      editor;


    /* ==================================================
     * EDITOR EVENTS
     * ================================================== */

    /*
     * При вводе обновляем состояние вкладки.
     */

    view.dom.addEventListener(
      "input",
      () => {
        markEmptyTabs();
      }
    );


    /*
     * При фокусе переключаем preview
     * на соответствующую вкладку.
     */

    view.dom.addEventListener(
      "focus",
      () => {
        showTab(name);
      }
    );


    return editor;
  }


  /* ==================================================
   * EDITOR CONTAINERS
   * ================================================== */

  function setupEditor(
    field,
    name
  ) {

    if (!field) {
      return null;
    }


    /*
     * Обычно textarea находится внутри
     * Django .form-row.
     */

    const row =
      field.closest(".form-row") ||
      field.parentElement;


    if (!row) {
      return null;
    }


    /*
     * Ищем уже созданный контейнер.
     */

    let container =
      row.querySelector(
        `.aether-editor[data-field="${name}"]`
      );


    /*
     * Если контейнера ещё нет —
     * создаём его.
     */

    if (!container) {

      container =
        document.createElement("div");

      container.className =
        "aether-editor";

      container.dataset.field =
        name;


      /*
       * CodeMirror появляется непосредственно
       * после оригинального textarea.
       */

      field.insertAdjacentElement(
        "afterend",
        container
      );

    }


    return createEditor(
      field,
      container,
      name
    );

  }


  /* ==================================================
   * CREATE BODY EDITOR
   * ================================================== */

  editors.body =
    setupEditor(
      fields.body,
      "body"
    );


  /* ==================================================
   * CREATE INFOBOX EDITOR
   * ================================================== */

  editors.infobox =
    setupEditor(
      fields.infobox,
      "infobox"
    );


  /* ==================================================
   * TAB SWITCHING
   * ================================================== */

  function showTab(name) {

    /*
     * Верхние tabs.
     */

    tabs.forEach(
      (tab) => {

        tab.classList.toggle(
          "is-active",
          tab.dataset.tab === name
        );

      }
    );


    /*
     * Preview frames.
     */

    Object.keys(frames).forEach(
      (key) => {

        if (!frames[key]) {
          return;
        }


        frames[key].classList.toggle(
          "is-active",
          key === name
        );

      }
    );


    /*
     * CodeMirror editors.
     */

    document
      .querySelectorAll(
        ".aether-editor"
      )
      .forEach(
        (editor) => {

          editor.classList.toggle(
            "is-active",
            editor.dataset.field === name
          );

        }
      );


    /*
     * CodeMirror должен пересчитать размеры,
     * если его контейнер только что стал видимым.
     */

    const editor =
      editors[name];


    if (editor) {

      requestAnimationFrame(
        () => {

          editor.view.requestMeasure();

        }
      );

    }


    /*
     * Preview тоже должен пересчитать ширину
     * после переключения iframe.
     */

    requestAnimationFrame(
      () => {

        resizePreviewFrame(
          frames[name]
        );

      }
    );

  }


  /* ==================================================
   * TAB EVENTS
   * ================================================== */

  tabs.forEach(
    (tab) => {

      tab.addEventListener(
        "click",
        () => {

          showTab(
            tab.dataset.tab
          );

        }
      );

    }
  );


  /* ==================================================
   * FIELD VALUE
   * ================================================== */

  function fieldValue(name) {

    /*
     * Для body / infobox источник истины —
     * состояние CodeMirror.
     */

    if (editors[name]) {

      return editors[name]
        .view
        .state
        .doc
        .toString();

    }


    /*
     * Для остальных полей —
     * обычный Django input.
     */

    return val(
      fields[name]
    );

  }


  /* ==================================================
   * EMPTY TABS
   * ================================================== */

  function markEmptyTabs() {

    tabs.forEach(
      (tab) => {

        const name =
          tab.dataset.tab;


        const value =
          fieldValue(name);


        tab.classList.toggle(
          "is-empty",
          !value.trim()
        );

      }
    );

  }


  /* ==================================================
   * PREVIEW PREFERENCES
   * ================================================== */

  function checkedKeys() {

    return keyBoxes()
      .filter(
        (box) => box.checked
      )
      .map(
        (box) => box.value
      );

  }


  function savePrefs() {

    try {

      localStorage.setItem(
        STORE,
        JSON.stringify({
          mode:
            asSelect.value,

          keys:
            checkedKeys(),
        })
      );

    } catch (e) {

      /*
       * localStorage может быть недоступен.
       * Это не критично.
       */

    }

  }


  function loadPrefs() {

    let prefs = {};


    try {

      prefs =
        JSON.parse(
          localStorage.getItem(
            STORE
          )
        ) || {};

    } catch (e) {

      prefs = {};

    }


    /*
     * Режим просмотра.
     */

    if (
      [
        "all",
        "none",
        "custom",
      ].includes(
        prefs.mode
      )
    ) {

      asSelect.value =
        prefs.mode;

    }


    /*
     * Сохранённые ключи.
     */

    const saved =
      Array.isArray(
        prefs.keys
      )
        ? prefs.keys
        : [];


    keyBoxes().forEach(
      (box) => {

        box.checked =
          saved.includes(
            box.value
          );

      }
    );


    keysBox.hidden =
      asSelect.value !==
      "custom";

  }


  /* ==================================================
   * SPLIT RESIZER
   * ================================================== */

  let splitRatio = 0.5;


  function splitIsStacked() {

    return window.innerWidth <=
      SPLIT_BREAKPOINT;

  }


  function applySplit() {

    if (
      !formPane ||
      !previewPane
    ) {
      return;
    }


    /*
     * На узких экранах возвращаем
     * стандартную одноколоночную схему.
     */

    if (splitIsStacked()) {

      root.style.gridTemplateColumns =
        "";

      root.style.columnGap =
        "";

      splitResizer.style.display =
        "none";

      return;
    }


    splitResizer.style.display =
      "block";


    /*
     * В исходном CSS у .wp-split
     * стоит gap: 20px.
     *
     * При наличии третьей колонки
     * этот gap применяется дважды.
     *
     * Divider сам является разделителем,
     * поэтому горизонтальный gap здесь
     * убираем.
     */

    root.style.columnGap =
      "0px";


    const total =
      root.clientWidth;


    if (!total) {
      return;
    }


    const available =
      total - SPLIT_DIVIDER;


    const minLeft =
      SPLIT_MIN_LEFT;

    const minRight =
      SPLIT_MIN_RIGHT;


    /*
     * Если места недостаточно даже
     * для минимальных размеров —
     * делим пространство поровну.
     */

    if (
      available <
      minLeft + minRight
    ) {

      root.style.gridTemplateColumns =
        `minmax(0, 1fr) ${SPLIT_DIVIDER}px minmax(0, 1fr)`;

      return;
    }


    const maxLeft =
      available - minRight;


    const left =
      Math.min(
        Math.max(
          available * splitRatio,
          minLeft
        ),
        maxLeft
      );


    root.style.gridTemplateColumns =
      `${left}px ${SPLIT_DIVIDER}px minmax(0, 1fr)`;

  }


  function saveSplit() {

    try {

      localStorage.setItem(
        SPLIT_STORE,
        String(splitRatio)
      );

    } catch (e) {

      /*
       * localStorage недоступен.
       */

    }

  }


  function loadSplit() {

    try {

      const value =
        parseFloat(
          localStorage.getItem(
            SPLIT_STORE
          )
        );


      if (
        Number.isFinite(value) &&
        value >= 0.2 &&
        value <= 0.8
      ) {

        splitRatio =
          value;

      }

    } catch (e) {

      /*
       * Оставляем 0.5.
       */

    }

  }


  let resizing = false;


  function startResize(event) {

    if (splitIsStacked()) {
      return;
    }


    event.preventDefault();


    resizing = true;


    root.classList.add(
      "is-resizing"
    );


    document.body.classList.add(
      "wp-is-resizing"
    );


    const move =
      (moveEvent) => {

        if (!resizing) {
          return;
        }


        const rect =
          root.getBoundingClientRect();


        const available =
          rect.width - SPLIT_DIVIDER;


        if (available <= 0) {
          return;
        }


        const x =
          moveEvent.clientX -
          rect.left;


        const ratio =
          (x - SPLIT_DIVIDER / 2) /
          available;


        splitRatio =
          Math.min(
            Math.max(
              ratio,
              0.2
            ),
            0.8
          );


        applySplit();


        /*
         * Пересчитываем ширину preview
         * прямо во время resize.
         */

        resizeAllPreviewFrames();

      };


    const stop =
      () => {

        if (!resizing) {
          return;
        }


        resizing = false;


        root.classList.remove(
          "is-resizing"
        );


        document.body.classList.remove(
          "wp-is-resizing"
        );


        document.removeEventListener(
          "pointermove",
          move
        );


        document.removeEventListener(
          "pointerup",
          stop
        );


        saveSplit();


        /*
         * Финальный пересчёт после окончания resize.
         */

        requestAnimationFrame(
          () => {

            resizeAllPreviewFrames();

          }
        );

      };


    document.addEventListener(
      "pointermove",
      move
    );


    document.addEventListener(
      "pointerup",
      stop
    );

  }


  splitResizer.addEventListener(
    "pointerdown",
    startResize
  );


  loadSplit();


  applySplit();


  window.addEventListener(
    "resize",
    () => {

      applySplit();


      requestAnimationFrame(
        () => {

          resizeAllPreviewFrames();

        }
      );

    }
  );


  /* ==================================================
   * PREVIEW STATUS
   * ================================================== */

  function setStatus(
    text,
    kind
  ) {

    statusEl.textContent =
      text;


    statusEl.dataset.kind =
      kind || "";

  }


  /* ==================================================
   * PREVIEW FRAME SIZE
   * ================================================== */

  function resizePreviewFrame(frame) {

    if (!frame || !previewViewport) {
      return;
    }


    try {

      const doc =
        frame.contentDocument;


      if (!doc) {
        return;
      }


      const body =
        doc.body;

      const html =
        doc.documentElement;


      if (!body || !html) {
        return;
      }


      /*
       * Ширина самого viewport.
       */

      const viewportWidth =
        Math.max(
          1,
          previewViewport.clientWidth
        );


      /*
       * --------------------------------------------------
       * НЕ СБРАСЫВАЕМ ШИРИНУ IFRAME.
       * --------------------------------------------------
       *
       * Это было причиной проблемы:
       *
       *   resize
       *       ↓
       *   iframe = viewport width
       *       ↓
       *   измерение
       *       ↓
       *   fixed-width документ теряет ширину
       *
       * Теперь iframe сохраняет свою текущую
       * ширину, а мы только определяем,
       * насколько шире viewport должен быть.
       */

      let contentWidth =
        Math.max(
          body.scrollWidth,
          html.scrollWidth,

          body.offsetWidth,
          html.offsetWidth
        );


      /*
       * --------------------------------------------------
       * Измеряем дочерние элементы.
       * --------------------------------------------------
       *
       * Некоторые документы имеют fixed-width
       * .page/.sheet/etc., но сам body при этом
       * может иметь ширину viewport.
       */

      const elements =
        doc.querySelectorAll("*");


      for (
        let i = 0;
        i < elements.length;
        i++
      ) {

        const element =
          elements[i];


        const rect =
          element.getBoundingClientRect();


        if (
          !rect.width ||
          !rect.height
        ) {
          continue;
        }


        /*
         * Правая граница элемента.
         */

        const right =
          rect.right;


        /*
         * Левая граница элемента.
         *
         * Нужна для элементов, которые выходят
         * за viewport влево.
         */

        const left =
          rect.left;


        contentWidth =
          Math.max(
            contentWidth,
            right,
            rect.width,
            right -
              Math.min(
                0,
                left
              )
          );

      }


      /*
       * --------------------------------------------------
       * Определяем итоговую ширину.
       * --------------------------------------------------
       */

      const targetWidth =
        Math.max(
          viewportWidth,
          Math.ceil(
            contentWidth
          )
        );


      /*
       * Именно здесь iframe становится шире
       * viewport, если его содержимое шире.
       */

      frame.style.width =
        `${targetWidth}px`;


      /*
       * Не позволяем iframe стать уже viewport.
       */

      frame.style.minWidth =
        `${viewportWidth}px`;


    } catch (error) {

      /*
       * iframe мог быть пересоздан
       * или ещё не успел загрузиться.
       */

    }

  }


  function resizeAllPreviewFrames() {

    Object.values(frames).forEach(
      (frame) => {

        resizePreviewFrame(
          frame
        );

      }
    );

  }


  /* ==================================================
   * PREVIEW FRAME
   * ================================================== */

  function show(
    frame,
    html
  ) {

    if (!frame) {
      return;
    }


    /*
     * Если HTML не изменился,
     * всё равно пересчитываем ширину.
     *
     * Это важно после resize split.
     */

    if (
      frame._last === html
    ) {

      requestAnimationFrame(
        () => {

          resizePreviewFrame(
            frame
          );

        }
      );

      return;
    }


    frame._last =
      html;


    /*
     * Запоминаем горизонтальную позицию
     * viewport.
     *
     * Именно viewport теперь отвечает
     * за горизонтальный scrollbar.
     */

    const viewportX =
      previewViewport
        ? previewViewport.scrollLeft
        : 0;


    /*
     * Вертикальная позиция остаётся
     * внутри iframe.
     */

    let y = 0;


    try {

      y =
        frame.contentWindow
          .scrollY || 0;

    } catch (e) {

      y = 0;

    }


    /*
     * После загрузки восстанавливаем
     * положение preview.
     */

    const restore =
      () => {

        frame.removeEventListener(
          "load",
          restore
        );


        /*
         * Первый кадр:
         *
         * iframe уже загружен,
         * браузер должен построить layout.
         */

        requestAnimationFrame(
          () => {

            resizePreviewFrame(
              frame
            );


            /*
             * Второй кадр:
             *
             * ширина iframe уже установлена.
             */

            requestAnimationFrame(
              () => {

                try {

                  /*
                   * Восстанавливаем
                   * горизонтальную позицию
                   * внешнего viewport.
                   */

                  previewViewport.scrollLeft =
                    viewportX;


                  /*
                   * Восстанавливаем
                   * вертикальную позицию
                   * документа.
                   */

                  frame.contentWindow
                    .scrollTo(
                      0,
                      y
                    );

                } catch (e) {

                  /*
                   * iframe мог быть ещё недоступен.
                   */

                }

              }
            );

          }
        );

      };


    frame.addEventListener(
      "load",
      restore
    );


    frame.srcdoc =
      html;

  }


  /* ==================================================
   * PREVIEW REQUEST
   * ================================================== */

  let timer = null;

  let controller = null;

  let seq = 0;


  async function refresh() {

    /*
     * Отменяем предыдущий запрос.
     */

    if (controller) {
      controller.abort();
    }


    controller =
      new AbortController();


    /*
     * Номер текущего запроса.
     *
     * Нужен на случай, если старый запрос
     * успел вернуться после нового.
     */

    const mine =
      ++seq;


    setStatus(
      "обновляется…"
    );


    /* ==================================================
     * PAYLOAD
     * ================================================== */

    const payload = {

      title:
        val(fields.title),

      type:
        val(fields.type),

      body:
        fieldValue("body"),

      infobox:
        fieldValue("infobox"),

      keys: {

        mode:
          asSelect.value,

        list:
          checkedKeys(),

      },

    };


    /* ==================================================
     * REQUEST
     * ================================================== */

    try {

      const resp =
        await fetch(
          previewUrl,
          {
            method: "POST",

            credentials:
              "same-origin",

            signal:
              controller.signal,

            headers: {

              "Content-Type":
                "application/json",

              "X-CSRFToken":
                csrf(),

            },

            body:
              JSON.stringify(
                payload
              ),

          }
        );


      /* ==================================================
       * RESPONSE
       * ================================================== */

      let data;


      try {

        data =
          await resp.json();

      } catch (e) {

        throw new Error(
          "сервер ответил не JSON " +
          "(возможно, истекла сессия админки)"
        );

      }


      /*
       * Если за это время появился
       * более новый запрос — старый результат
       * игнорируем.
       */

      if (mine !== seq) {
        return;
      }


      if (
        !resp.ok ||
        !data.ok
      ) {

        throw new Error(
          data.error ||
          "HTTP " +
          resp.status
        );

      }


      /* ==================================================
       * UPDATE PREVIEW
       * ================================================== */

      show(
        frames.body,
        data.body
      );


      show(
        frames.infobox,
        data.infobox
      );


      setStatus(
        "обновлено " +
        new Date()
          .toLocaleTimeString(
            "ru-RU"
          )
      );


    } catch (e) {

      /*
       * Abort — нормальная ситуация.
       */

      if (
        e.name ===
        "AbortError"
      ) {
        return;
      }


      /*
       * Предыдущий успешный preview
       * остаётся на экране.
       */

      setStatus(
        "ошибка: " +
        e.message,
        "error"
      );

    }

  }


  /* ==================================================
   * PREVIEW SCHEDULER
   * ================================================== */

  function schedule() {

    clearTimeout(
      timer
    );


    markEmptyTabs();


    setStatus(
      "…"
    );


    timer =
      setTimeout(
        refresh,
        DELAY_MS
      );

  }


  /* ==================================================
   * TITLE
   * ================================================== */

  if (fields.title) {

    fields.title.addEventListener(
      "input",
      schedule
    );

  }


  /* ==================================================
   * TYPE
   * ================================================== */

  if (fields.type) {

    fields.type.addEventListener(
      "change",
      schedule
    );

  }


  /* ==================================================
   * BODY
   * ================================================== */

  if (fields.body) {

    fields.body.addEventListener(
      "input",
      schedule
    );

  }


  /* ==================================================
   * INFOBOX
   * ================================================== */

  if (fields.infobox) {

    fields.infobox.addEventListener(
      "input",
      schedule
    );

  }


  /* ==================================================
   * "СМОТРЕТЬ КАК"
   * ================================================== */

  asSelect.addEventListener(
    "change",
    () => {

      keysBox.hidden =
        asSelect.value !==
        "custom";


      savePrefs();

      schedule();

    }
  );


  /* ==================================================
   * KEY SELECTION
   * ================================================== */

  keysBox.addEventListener(
    "change",
    () => {

      savePrefs();

      schedule();

    }
  );


  /* ==================================================
   * CONDITION EDITORS
   * ================================================== */

  function initConditionEditors() {

    const keysElement =
      document.getElementById(
        "wiki-condition-keys"
      );

    let keys = [];

    if (keysElement) {

      try {

        keys =
          JSON.parse(
            keysElement.textContent
          );

      } catch (error) {

        console.error(
          "Failed to parse condition keys:",
          error
        );

      }

    }


    const visibility =
      document.getElementById(
        "id_visibility"
      );

    const access =
      document.getElementById(
        "id_access"
      );


    if (visibility) {

      window.AetherConditionEditor.create(
        visibility,
        {
          title: "Visibility",
          keys,
        }
      );

    }


    if (access) {

      window.AetherConditionEditor.create(
        access,
        {
          title: "Access",
          keys,
        }
      );

    }

  }


  /* ==================================================
   * INIT
   * ================================================== */

  initConditionEditors();

  loadPrefs();

  markEmptyTabs();

  showTab("body");

  refresh();

})();