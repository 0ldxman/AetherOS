// Язык сцен в CodeMirror: подсветка, автодополнение (@шаги, <теги>, {подстановки}) и пометки ошибок прямо в строках.
import { HighlightStyle, StreamLanguage, syntaxHighlighting } from "@codemirror/language";
import { autocompletion, snippet, type Completion, type CompletionContext } from "@codemirror/autocomplete";
import { RangeSetBuilder, StateEffect, StateField, type Extension } from "@codemirror/state";
import { Decoration, EditorView, GutterMarker, gutter } from "@codemirror/view";
import { tags as t } from "@lezer/highlight";
import { STEP_WORDS, TAG_WORDS, type Snip } from "./catalog";

export type Problem = { line: number; text: string };

const language = StreamLanguage.define<Record<string, never>>({
  token(stream) {
    if (stream.sol()) {
      if (stream.match(/^#.*/)) return "comment";
      if (stream.match(/^~(?: .*)?$/)) return "quote";
      if (stream.match(/^@[A-Za-z]+/)) return "keyword";
    }
    if (stream.match(/\{[A-Za-z_]\w*\}/)) return "variableName";
    if (stream.match(/<\/?[a-z]+[^>]*>/)) return "tagName";
    if (stream.match(/&(?:lt|gt|amp|pipe);/)) return "escape";
    if (stream.match(/\|/)) return "operator";
    if (stream.match(/[\p{L}_][\p{L}\d_]*/u)) return null;
    if (stream.match(/\d+(?:\.\d+)?(?:-\d+)?/)) return "number";
    stream.next();
    return null;
  },
});

const style = HighlightStyle.define([
  { tag: t.comment, color: "#818996", fontStyle: "italic" },
  { tag: t.keyword, color: "#7aa2ff", fontWeight: "600" },
  { tag: t.tagName, color: "#c792ea" },
  { tag: t.variableName, color: "#f2c66d" },
  { tag: t.operator, color: "#818996" },
  { tag: t.number, color: "#5fd0a0" },
  { tag: t.quote, color: "#9097a3" },
  { tag: t.escape, color: "#f2c66d" },
]);

// ---------- ошибки в строках ----------
const setProblems = StateEffect.define<Problem[]>();

class Dot extends GutterMarker {
  constructor(private text: string) { super(); }
  eq(other: Dot) { return other.text === this.text; }
  toDOM() {
    const node = document.createElement("span");
    node.className = "scene-dot";
    node.textContent = "●";
    node.title = this.text;
    return node;
  }
}

const problems = StateField.define<{ list: Problem[] }>({
  create: () => ({ list: [] }),
  update(value, tr) {
    for (const effect of tr.effects) if (effect.is(setProblems)) return { list: effect.value };
    return value;
  },
});

const marks = EditorView.decorations.compute([problems], (state) => {
  const builder = new RangeSetBuilder<Decoration>();
  const byLine = new Map<number, string[]>();
  for (const item of state.field(problems).list) byLine.set(item.line, [...(byLine.get(item.line) ?? []), item.text]);
  for (const number of [...byLine.keys()].sort((a, b) => a - b)) {
    if (number < 1 || number > state.doc.lines) continue;
    const line = state.doc.line(number);
    if (line.length) builder.add(line.from, line.to, Decoration.mark({ class: "scene-bad", attributes: { title: byLine.get(number)!.join("\n") } }));
  }
  return builder.finish();
});

const dots = gutter({
  class: "scene-gutter",
  lineMarker(view, block) {
    const number = view.state.doc.lineAt(block.from).number;
    const found = view.state.field(problems).list.filter((item) => item.line === number);
    return found.length ? new Dot(found.map((item) => item.text).join("\n")) : null;
  },
  lineMarkerChange: (update) => update.transactions.some((tr) => tr.effects.some((effect) => effect.is(setProblems))),
  initialSpacer: () => new Dot(""),
});

export function showProblems(view: EditorView, list: Problem[]) {
  view.dispatch({ effects: setProblems.of(list) });
}

// ---------- автодополнение ----------
const option = (item: Snip): Completion => ({ label: item.code, detail: item.args, info: `${item.title}. ${item.doc}`, type: item.code.startsWith("@") ? "keyword" : "type", apply: snippet(item.template) });

export function sceneSupport(getParams: () => string[]): Extension {
  const source = (context: CompletionContext) => {
    const line = context.state.doc.lineAt(context.pos);
    const before = line.text.slice(0, context.pos - line.from);
    let found: RegExpExecArray | null;
    if ((found = /^@\w*$/.exec(before))) return { from: context.pos - found[0].length, options: STEP_WORDS.map(option), validFor: /^@\w*$/ };
    if ((found = /<\/?\w*$/.exec(before))) return { from: context.pos - found[0].length, options: TAG_WORDS.map(option), validFor: /^<\/?\w*$/ };
    if ((found = /\{\w*$/.exec(before))) {
      return { from: context.pos - found[0].length, options: getParams().map((name): Completion => ({ label: `{${name}}`, type: "variable", detail: "подстановка" })), validFor: /^\{\w*$/ };
    }
    return null;
  };
  const theme = EditorView.theme({
    ".scene-bad": { textDecoration: "underline wavy var(--warn)", textUnderlineOffset: "3px" },
    ".scene-gutter": { width: "14px" },
    ".scene-dot": { color: "var(--warn)", fontSize: "9px", cursor: "help" },
    ".cm-tooltip.cm-tooltip-autocomplete": { backgroundColor: "var(--raise)", border: "1px solid var(--line)", borderRadius: "8px" },
    ".cm-tooltip-autocomplete ul li[aria-selected]": { backgroundColor: "var(--accent-soft)", color: "var(--text)" },
    ".cm-completionDetail": { color: "var(--faint)", marginLeft: "8px", fontStyle: "normal" },
    ".cm-completionInfo": { backgroundColor: "var(--raise)", border: "1px solid var(--line)", borderRadius: "8px", color: "var(--muted)", padding: "6px 10px" },
  }, { dark: true });
  return [language, syntaxHighlighting(style), problems, marks, dots, autocompletion({ override: [source], icons: false }), theme];
}
