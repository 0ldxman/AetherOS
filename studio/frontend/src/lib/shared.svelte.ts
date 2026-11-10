// Форма редактора, привязанная к общему черновику комнаты (team.collab): поля живут в документе Yjs комнаты.
//
// Комната это сущность на экране (machines/3), в ней может быть несколько форм: у каждой своя область (scope), например
// учётка 4 на машине 3. Тексты (texts) это общий текст Y.Text: CodeEditor правит его напрямую, с курсорами других; простые
// поля ввода переписывают его по разнице. Остальные поля формы это общие значения: побеждает последнее изменение, списки и
// словари сравниваются по содержимому. Пока черновик области чистый, он наполняется из сохранённого в мире (base); своя
// правка ставит метку «не сохранено» с именем автора, сохранение её снимает и сообщает остальным (onRemoteSave).
import { untrack } from "svelte";
import * as Y from "yjs";
import { claim, presence, roomDoc } from "./collab.svelte";

/** Комната с номером сущности (не «машина null», пока запись не выбрана). */
const real = (room: string) => !!room && !/\/(null|undefined|0)?$/.test(room);
import { flashAround } from "./marks.svelte";

type Values = Record<string, unknown>;
type Mark = { dirty?: boolean; editors?: string[]; saved?: number };

type Options<T> = {
  room: () => string;               // своя комната (путь API сущности): чужой, ещё не сменившийся документ не берётся
  scope?: () => string;             // область формы в комнате (по умолчанию main)
  texts?: (keyof T & string)[];
  values?: (keyof T & string)[];    // по умолчанию все остальные поля сохранённого
  draft: () => T;
  base: () => T | null;
  onRemoteSave?: () => void;
};

const same = (a: unknown, b: unknown) => a === b || (typeof a === "object" && typeof b === "object" && JSON.stringify(a) === JSON.stringify(b));
const copy = (value: unknown) => (value !== null && typeof value === "object" ? JSON.parse(JSON.stringify(value)) : value ?? null);

export class SharedForm<T extends Values> {
  texts = $state.raw<Record<string, Y.Text>>({});
  ready = $state(false);
  editors = $state<string[]>([]);
  dirty = $state(false);

  private doc: Y.Doc | null = null;
  private fields: Y.Map<unknown> | null = null;
  private meta: Y.Map<unknown> | null = null;
  private key = "main";
  private lastSaved = 0;
  private stop: (() => void) | null = null;

  constructor(private options: Options<T>) {
    $effect(() => {
      const room = options.room();
      if (real(room)) return claim(room);
    });
    $effect(() => {
      presence.epoch;
      const synced = presence.synced;
      const base = options.base();
      const scope = options.scope?.() ?? "main";
      if (!synced || !base || presence.room !== options.room()) return;
      untrack(() => this.attach(base, scope));
    });
    $effect(() => {
      const draft = options.draft();
      const snapshot: Values = {};
      for (const key of Object.keys(draft)) snapshot[key] = $state.snapshot(draft[key]);
      if (!this.ready) return;
      untrack(() => this.push(snapshot));
    });
    $effect(() => () => this.detach());
  }

  private textKeys(): string[] {
    const base = this.options.base();
    return (this.options.texts ?? []).filter((key) => !base || key in base);     // поля, которых у формы нет, не добавляются
  }

  private valueKeys(base: Values | null): string[] {
    if (this.options.values) return this.options.values;
    const texts = new Set(this.textKeys());
    return Object.keys(base ?? this.options.base() ?? this.options.draft()).filter((key) => !texts.has(key));
  }

  private mark(): Mark {
    return (this.meta?.get(this.key) as Mark | undefined) ?? {};
  }

  private attach(base: T, scope: string) {
    const doc = roomDoc();
    if (!doc) return;
    if (doc !== this.doc || scope !== this.key) {
      this.detach();
      this.doc = doc;
      this.key = scope;
      this.fields = doc.getMap(`fields:${scope}`);
      this.meta = doc.getMap("_meta");
      const fields = this.fields;
      const meta = this.meta;
      const onFields = (_events: unknown, transaction: Y.Transaction) => {
        if (transaction.local) this.pull();
        else flashAround(() => this.pull());
      };
      const onMeta = (event: Y.YMapEvent<unknown>, transaction: Y.Transaction) => {
        if (!event.keysChanged.has(this.key)) return;
        const before = this.lastSaved;
        this.readMark();
        if (!transaction.local && this.lastSaved !== before) this.options.onRemoteSave?.();
      };
      const onTransaction = (transaction: Y.Transaction) => {
        if (!transaction.local || transaction.origin === "seed" || transaction.origin === "saved" || transaction.origin === "meta") return;
        if (![...transaction.changed.keys()].some((type) => (type as unknown) === fields || isInside(type, fields))) return;
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
    this.readMark();
    this.pull();
    this.ready = true;
  }

  private readMark() {
    const mark = this.mark();
    this.editors = mark.editors ?? [];
    this.dirty = !!mark.dirty;
    this.lastSaved = mark.saved ?? 0;
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
    const clean = !this.mark().dirty;
    this.doc!.transact(() => {
      for (const key of this.textKeys()) {
        const value = String(base[key] ?? "");
        const found = fields.get(key);
        if (!(found instanceof Y.Text)) fields.set(key, new Y.Text(value));
        else if (clean && found.toString() !== value) replaceText(found, value);
      }
      for (const key of this.valueKeys(base)) {
        const value = copy(base[key]);
        if (!fields.has(key) || (clean && !same(fields.get(key), value))) fields.set(key, value);
      }
    }, "seed");
  }

  /** Черновик комнаты в форму экрана. */
  private pull() {
    const fields = this.fields;
    if (!fields) return;
    const draft = this.options.draft();
    const texts: Record<string, Y.Text> = {};
    for (const key of this.textKeys()) {
      const found = fields.get(key);
      if (found instanceof Y.Text) {
        texts[key] = found;
        const value = found.toString();
        if (draft[key] !== value) (draft as Values)[key] = value;
      }
    }
    for (const key of this.valueKeys(null)) {
      if (!fields.has(key)) continue;
      const value = fields.get(key);
      if (!same(draft[key], value)) (draft as Values)[key] = copy(value);
    }
    if (Object.keys(texts).some((key) => texts[key] !== this.texts[key])) this.texts = texts;
  }

  /** Форма экрана в черновик комнаты (простые поля ввода; CodeEditor пишет в общий текст сам). */
  private push(snapshot: Values) {
    const fields = this.fields;
    if (!fields || !this.doc) return;
    this.doc.transact(() => {
      for (const key of this.textKeys()) {
        const found = fields.get(key);
        const value = String(snapshot[key] ?? "");
        if (found instanceof Y.Text && found.toString() !== value) replaceText(found, value);
      }
      for (const key of this.valueKeys(null)) {
        if (!(key in snapshot)) continue;
        const value = copy(snapshot[key]);
        if (!same(fields.get(key), value)) fields.set(key, value);
      }
    });
  }

  private setMark(next: Mark, origin: string) {
    const meta = this.meta;
    if (!meta || !this.doc) return;
    this.doc.transact(() => meta.set(this.key, next), origin);
  }

  private markDirty() {
    const mark = this.mark();
    const me = presence.me;
    const editors = mark.editors ?? [];
    if (mark.dirty && (!me || editors.includes(me))) return;
    this.setMark({ ...mark, dirty: true, editors: me && !editors.includes(me) ? [...editors, me] : editors }, "meta");
  }

  /** Отменить правки черновика: вернуть всем в комнате сохранённое в мире и снять метку. */
  discard() {
    const base = this.options.base();
    const fields = this.fields;
    if (!base || !fields || !this.doc) return;
    this.doc.transact(() => {
      for (const key of this.textKeys()) {
        const found = fields.get(key);
        if (found instanceof Y.Text) replaceText(found, String(base[key] ?? ""));
      }
      for (const key of this.valueKeys(base)) fields.set(key, copy(base[key]));
    }, "saved");
    this.setMark({ dirty: false, editors: [], saved: this.mark().saved ?? 0 }, "saved");
    this.pull();
  }

  /** Сохранено в мир: снять метку «не сохранено» и сообщить остальным в комнате. */
  markSaved() {
    this.lastSaved = Date.now();
    this.setMark({ dirty: false, editors: [], saved: this.lastSaved }, "saved");
  }
}

function isInside(type: unknown, parent: Y.Map<unknown>): boolean {
  let node = (type as { _item?: { parent?: unknown } | null })._item?.parent;
  while (node) {
    if (node === parent) return true;
    node = (node as { _item?: { parent?: unknown } | null })._item?.parent;
  }
  return false;
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

/** Экран, который применяет правки сразу (без черновика): после любой своей правки через API клиент сообщает комнате
 *  (collab.touched), остальные на этой странице перечитывают данные (onPing), изменившееся подсвечивается. */
export class RoomPing {
  private doc: Y.Doc | null = null;
  private stop: (() => void) | null = null;

  constructor(private options: { room: () => string; scope?: () => string; onPing: () => void | Promise<void> }) {
    $effect(() => {
      const room = options.room();
      if (real(room)) return claim(room);
    });
    $effect(() => {
      presence.epoch;
      const synced = presence.synced;
      if (!synced || presence.room !== options.room()) return;
      untrack(() => this.attach());
    });
    $effect(() => () => this.stop?.());
  }

  private key() {
    return this.options.scope?.() ?? "writes";
  }

  private attach() {
    const doc = roomDoc();
    if (!doc || doc === this.doc) return;
    this.stop?.();
    this.doc = doc;
    const pings = doc.getMap("pings");
    const onPing = (event: Y.YMapEvent<unknown>, transaction: Y.Transaction) => {
      if (!transaction.local && event.keysChanged.has(this.key())) flashAround(this.options.onPing);
    };
    pings.observe(onPing);
    this.stop = () => pings.unobserve(onPing);
  }

  send() {
    this.doc?.getMap("pings").set(this.key(), Date.now());
  }
}
