<script lang="ts">
  // CodeMirror с нашей разметкой (подсветка, сворачивание блоков) или простым текстом. Ctrl+S зовёт onsave.
  // shared: общий текст комнаты (team.collab): правка идёт прямо в него, видны курсоры и выделения других авторов.
  // Такой редактор пересоздаётся, если сменился общий текст (снаружи: {#key}).
  import { onMount } from "svelte";
  import { Compartment, EditorState } from "@codemirror/state";
  import { EditorView, drawSelection, highlightActiveLine, highlightActiveLineGutter, keymap, lineNumbers } from "@codemirror/view";
  import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
  import { syntaxHighlighting } from "@codemirror/language";
  import { highlightSelectionMatches, searchKeymap } from "@codemirror/search";
  // @ts-expect-error общий со старым редактором JS без типов
  import { aetherLanguage } from "$documents/editor/aether-language.js";
  // @ts-expect-error то же
  import { aetherFoldGutter, aetherFoldService } from "$documents/editor/aether-fold.js";
  // @ts-expect-error то же
  import { aetherHighlightStyle } from "$documents/editor/aether-theme.js";
  import * as Y from "yjs";
  import { yCollab, yUndoManagerKeymap } from "y-codemirror.next";
  import { focusField, roomAwareness } from "./collab.svelte";
  import { snippet } from "@codemirror/autocomplete";
  import { sceneSupport, showProblems, type Problem } from "./scene/sceneLang";

  let { value = $bindable(""), markup = false, readonly = false, onsave, shared = null, field = "", scene = null }: {
    value?: string;
    markup?: boolean;
    readonly?: boolean;
    onsave?: () => void;
    shared?: Y.Text | null;
    field?: string;               // как поле назвать другим авторам, когда здесь фокус
    scene?: { problems: Problem[]; params: string[] } | null;     // язык сцен: подсветка, подсказки, ошибки в строках
  } = $props();

  let host: HTMLDivElement;

  /** Вставить шаблон (поля ${1:имя} заполняются по Tab) на место курсора. */
  export function insertSnippet(template: string) {
    if (!view) return;
    const { from, to } = view.state.selection.main;
    view.focus();
    snippet(template)(view, null, from, to);
  }
  /** Вставить текст на место курсора. */
  export function insertText(text: string) {
    if (!view) return;
    view.focus();
    view.dispatch(view.state.replaceSelection(text), { scrollIntoView: true });
  }
  /** Перейти к строке и выделить её. */
  export function goto(number: number) {
    if (!view || number < 1 || number > view.state.doc.lines) return;
    const line = view.state.doc.line(number);
    view.focus();
    view.dispatch({ selection: { anchor: line.from, head: line.to }, scrollIntoView: true });
  }
  let view: EditorView;
  let sceneParams: string[] = [];
  const language = new Compartment();
  const editable = new Compartment();

  const theme = EditorView.theme({
    "&": { height: "100%", fontSize: "13px", backgroundColor: "var(--bg)" },
    ".cm-scroller": { fontFamily: "var(--mono)", lineHeight: "1.6" },
    ".cm-content": { padding: "12px 0", caretColor: "var(--accent)" },
    ".cm-line": { padding: "0 16px 0 8px" },
    ".cm-gutters": { backgroundColor: "var(--bg)", color: "var(--faint)", border: "none" },
    ".cm-activeLine": { backgroundColor: "rgba(255,255,255,.025)" },
    ".cm-activeLineGutter": { backgroundColor: "transparent", color: "var(--muted)" },
    ".cm-cursor": { borderLeftWidth: "2px", borderLeftColor: "var(--accent)" },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": { backgroundColor: "rgba(122,162,255,.22) !important" },
    ".cm-panels": { backgroundColor: "var(--panel)", color: "var(--text)" },
    ".cm-searchMatch": { backgroundColor: "rgba(242,198,109,.25)" },
  }, { dark: true });

  function languageFor(on: boolean) {
    return on ? [aetherLanguage, aetherFoldService, aetherFoldGutter, syntaxHighlighting(aetherHighlightStyle)] : [];
  }

  onMount(() => {
    const awareness = roomAwareness();
    const together = shared && awareness
      ? [yCollab(shared, awareness, { undoManager: new Y.UndoManager(shared) }), keymap.of(yUndoManagerKeymap)]
      : [history(), keymap.of(historyKeymap)];
    view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: shared && awareness ? shared.toString() : value,
        extensions: [
          lineNumbers(), drawSelection(), highlightActiveLine(), highlightActiveLineGutter(), highlightSelectionMatches(),
          together,
          EditorView.domEventHandlers({ focus: () => { if (field) focusField(field); }, blur: () => { if (field) focusField(""); } }),
          EditorView.lineWrapping, theme,
          language.of(languageFor(markup)),
          scene ? sceneSupport(() => sceneParams) : [],
          editable.of(EditorState.readOnly.of(readonly)),
          keymap.of([
            { key: "Mod-s", preventDefault: true, run: () => { onsave?.(); return true; } },
            indentWithTab, ...defaultKeymap, ...searchKeymap,
          ]),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) value = update.state.doc.toString();
          }),
        ],
      }),
    });
    return () => view.destroy();
  });

  // снаружи пришёл другой текст (восстановили версию, перечитали объект): заменяем без потери положения прокрутки
  $effect(() => {
    if (view && !shared && value !== view.state.doc.toString()) {      // общий текст правится через Yjs, не отсюда
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } });
    }
  });
  $effect(() => {
    view?.dispatch({ effects: language.reconfigure(languageFor(markup)) });
  });
  $effect(() => {
    sceneParams = scene?.params ?? [];
    if (view && scene) showProblems(view, scene.problems);
  });
  $effect(() => {
    view?.dispatch({ effects: editable.reconfigure(EditorState.readOnly.of(readonly)) });
  });
</script>

<div class="code" bind:this={host}></div>

<style>
  .code { height: 100%; min-height: 0; overflow: hidden; }
  .code :global(.cm-ySelectionInfo) { font: 600 10.5px/1.2 var(--sans, system-ui); padding: 1px 4px; border-radius: 3px 3px 3px 0; opacity: 1; top: -1.2em; }
  .code :global(.cm-ySelectionCaret) { border-left-width: 2px; }
</style>
