<script lang="ts">
  // CodeMirror с нашей разметкой (подсветка, сворачивание блоков) или простым текстом. Ctrl+S зовёт onsave.
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

  let { value = $bindable(""), markup = false, readonly = false, onsave }: {
    value?: string;
    markup?: boolean;
    readonly?: boolean;
    onsave?: () => void;
  } = $props();

  let host: HTMLDivElement;
  let view: EditorView;
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
    view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(), history(), drawSelection(), highlightActiveLine(), highlightActiveLineGutter(), highlightSelectionMatches(),
          EditorView.lineWrapping, theme,
          language.of(languageFor(markup)),
          editable.of(EditorState.readOnly.of(readonly)),
          keymap.of([
            { key: "Mod-s", preventDefault: true, run: () => { onsave?.(); return true; } },
            indentWithTab, ...defaultKeymap, ...historyKeymap, ...searchKeymap,
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
    if (view && value !== view.state.doc.toString()) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } });
    }
  });
  $effect(() => {
    view?.dispatch({ effects: language.reconfigure(languageFor(markup)) });
  });
  $effect(() => {
    view?.dispatch({ effects: editable.reconfigure(EditorState.readOnly.of(readonly)) });
  });
</script>

<div class="code" bind:this={host}></div>

<style>
  .code { height: 100%; min-height: 0; overflow: hidden; }
</style>
