// Форма редактора, привязанная к общему черновику комнаты (team.collab): поля живут в документе Yjs комнаты.
//
// Тексты (texts) это общий текст Y.Text: CodeEditor правит его напрямую, с курсорами других; простые поля ввода
// переписывают его по разнице. Остальные поля (values) это значения общей карты: побеждает последнее изменение.
// Пока черновик чистый, он наполняется из сохранённого в мире (base); своя правка ставит в карте _meta метку «не сохранено»
// с именем автора, сохранение её снимает и сообщает остальным (onRemoteSave), чтобы они перечитали версию.
import { untrack } from "svelte";
import * as Y from "yjs";
import { presence, roomDoc } from "./collab.svelte";

type Values = Record<string, unknown>;

type Options<T> = {
  room: () => string;               // своя комната (путь API сущности): чужой, ещё не сменившийся документ не берётся
  texts: (keyof T & string)[];
  values: (keyof T & string)[];
  draft: () => T;
  base: () => T | null;
  onRemoteSave?: () => void;
};

export class SharedForm<T extends Values> {
  texts = $state.raw<Record<string, Y.Text>>({});
  ready = $state(false);
  editors = $state<string[]>([]);
  dirty = $state(false);

  private doc: Y.Doc | null = null;
  private fields: Y.Map<unknown> | null = null;
  private meta: Y.Map<unknown> | null = null;
  private stop: (() => void) | null = null;

  constructor(private options: Options<T>) {
    $effect(() => {
      presence.epoch;
      const synced = presence.synced;
      const base = options.base();
      if (!synced || !base || presence.room !== options.room()) return;
      untrack(() => this.attach(base));
    });
    $effect(() => {
      const draft = options.draft();
      const snapshot: Values = {};
      for (const key of [...options.texts, ...options.values]) snapshot[key] = draft[key];
      if (!this.ready) return;
      untrack(() => this.push(snapshot));
    });
    $effect(() => () => this.detach());
  }

  private attach(base: T) {
    const doc = roomDoc();
    if (!doc) return;
    if (doc !== this.doc) {
      this.detach();
      this.doc = doc;
      this.fields = doc.getMap("fields");
      this.meta = doc.getMap("_meta");
      const fields = this.fields;
      const meta = this.meta;
      const onFields = () => this.pull();
      const onMeta = (event: Y.YMapEvent<unknown>, transaction: Y.Transaction) => {
        this.editors = (meta.get("editors") as string[] | undefined) ?? [];
        this.dirty = !!meta.get("dirty");
        if (!transaction.local && event.keysChanged.has("saved")) this.options.onRemoteSave?.();
      };
      const onTransaction = (transaction: Y.Transaction) => {
        if (!transaction.local || transaction.origin === "seed" || transaction.origin === "saved" || transaction.origin === "meta") return;
        if (![...transaction.changed.keys()].some((type) => (type as unknown) !== meta)) return;
        this.markDirty();
      };
      fields.observeDeep(onFields);
      meta.observe(onMeta);
      doc.on("afterTransaction", onTransaction);
      this.stop = () => {
        fields.unobserveDeep(onFields);
        meta.unobserve(onMeta);
        doc.off("afterTransaction", onTransaction);
      };
    }
    this.seed(base);
    this.editors = (this.meta!.get("editors") as string[] | undefined) ?? [];
    this.dirty = !!this.meta!.get("dirty");
    this.pull();
    this.ready = true;
  }

  private detach() {
    this.stop?.();
    this.stop = null;
    this.doc = this.fields = this.meta = null;
    this.ready = false;
    this.texts = {};
  }

  /** Наполнить черновик из сохранённого: пустые поля всегда, а чистый черновик ещё и подтянуть к миру. */
  private seed(base: T) {
    const fields = this.fields!;
    const clean = !this.meta!.get("dirty");
    this.doc!.transact(() => {
      for (const key of this.options.texts) {
        const value = String(base[key] ?? "");
        const found = fields.get(key);
        if (!(found instanceof Y.Text)) fields.set(key, new Y.Text(value));
        else if (clean && found.toString() !== value) replaceText(found, value);
      }
      for (const key of this.options.values) {
        const value = base[key] ?? null;
        if (!fields.has(key) || (clean && fields.get(key) !== value)) fields.set(key, value);
      }
    }, "seed");
  }

  /** Черновик комнаты в форму экрана. */
  private pull() {
    const fields = this.fields;
    if (!fields) return;
    const draft = this.options.draft();
    const texts: Record<string, Y.Text> = {};
    for (const key of this.options.texts) {
      const found = fields.get(key);
      if (found instanceof Y.Text) {
        texts[key] = found;
        const value = found.toString();
        if (draft[key] !== value) (draft as Values)[key] = value;
      }
    }
    for (const key of this.options.values) {
      if (!fields.has(key)) continue;
      const value = fields.get(key);
      if (draft[key] !== value) (draft as Values)[key] = value;
    }
    if (Object.keys(texts).some((key) => texts[key] !== this.texts[key])) this.texts = texts;
  }

  /** Форма экрана в черновик комнаты (простые поля ввода; CodeEditor пишет в общий текст сам). */
  private push(snapshot: Values) {
    const fields = this.fields;
    if (!fields || !this.doc) return;
    this.doc.transact(() => {
      for (const key of this.options.texts) {
        const found = fields.get(key);
        const value = String(snapshot[key] ?? "");
        if (found instanceof Y.Text && found.toString() !== value) replaceText(found, value);
      }
      for (const key of this.options.values) {
        const value = snapshot[key] ?? null;
        if (fields.get(key) !== value) fields.set(key, value);
      }
    });
  }

  private markDirty() {
    const meta = this.meta!;
    const me = presence.me;
    this.doc!.transact(() => {
      if (!meta.get("dirty")) meta.set("dirty", true);
      const editors = (meta.get("editors") as string[] | undefined) ?? [];
      if (me && !editors.includes(me)) meta.set("editors", [...editors, me]);
    }, "meta");
  }

  /** Отменить правки черновика: вернуть всем в комнате сохранённое в мире и снять метку. */
  discard() {
    const base = this.options.base();
    const fields = this.fields;
    const meta = this.meta;
    if (!base || !fields || !meta || !this.doc) return;
    this.doc.transact(() => {
      for (const key of this.options.texts) {
        const found = fields.get(key);
        if (found instanceof Y.Text) replaceText(found, String(base[key] ?? ""));
      }
      for (const key of this.options.values) fields.set(key, base[key] ?? null);
      meta.set("dirty", false);
      meta.set("editors", []);
    }, "saved");
    this.pull();
  }

  /** Сохранено в мир: снять метку «не сохранено» и сообщить остальным в комнате. */
  markSaved() {
    const meta = this.meta;
    if (!meta || !this.doc) return;
    this.doc.transact(() => {
      meta.set("dirty", false);
      meta.set("editors", []);
      meta.set("saved", Date.now());
    }, "saved");
  }
}

/** Заменить общий текст на новый по разнице (общее начало и конец не трогаются: чужой курсор там не прыгает). */
export function replaceText(text: Y.Text, next: string) {
  const current = text.toString();
  if (current === next) return;
  let start = 0;
  while (start < current.length && start < next.length && current[start] === next[start]) start++;
  let end = 0;
  while (end < current.length - start && end < next.length - start && current[current.length - 1 - end] === next[next.length - 1 - end]) end++;
  const removed = current.length - start - end;
  if (removed > 0) text.delete(start, removed);
  const inserted = next.slice(start, next.length - end);
  if (inserted) text.insert(start, inserted);
}
