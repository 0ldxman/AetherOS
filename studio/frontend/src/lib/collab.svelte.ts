// Совместная правка (team.collab): комната Yjs сущности, на странице которой автор сейчас. Одна комната на страницу:
// присутствие (кто здесь, где его фокус) и общий документ, к которому редакторы привязывают свои поля.
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";

export type Peer = { id: number; name: string; color: string; field: string };

// epoch растёт при каждой смене комнаты: по нему редакторы заново берут документ (roomDoc) и присутствие (roomAwareness)
export const presence = $state<{ room: string; peers: Peer[]; connected: boolean; synced: boolean; epoch: number; me: string }>(
  { room: "", peers: [], connected: false, synced: false, epoch: 0, me: "" },
);

let current: { room: string; doc: Y.Doc; provider: WebsocketProvider } | null = null;

// комнату заявляет редактор на экране (список с первой записью по умолчанию: в адресе её нет); без заявки берётся адрес
export const claimed = $state({ room: "" });

/** Редактор заявляет свою комнату; возвращает отказ от заявки (при уходе с экрана). */
export function claim(room: string): () => void {
  claimed.room = room;
  return () => { if (claimed.room === room) claimed.room = ""; };
}

const COLORS = ["#e5484d", "#f76b15", "#ffc53d", "#46a758", "#12a594", "#0090ff", "#8e4ec6", "#d6409f"];

/** Цвет автора: один и тот же у одного имени на всех страницах. */
export function colorOf(name: string): string {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return COLORS[hash % COLORS.length];
}

function serverUrl(): string {
  const api = new URL(window.STUDIO.api, location.href);
  const base = api.pathname.replace(/studio\/api\/?$/, "studio/ws");
  return `${location.protocol === "https:" ? "wss" : "ws"}://${api.host}${base}`;
}

/** Войти в комнату сущности (выйти из прежней). Пустая комната: страница без сущности. */
export function enter(room: string, name: string): void {
  if (current?.room === room) return;
  leave();
  presence.room = room;
  if (!room || !name) return;
  const doc = new Y.Doc();
  const provider = new WebsocketProvider(serverUrl(), room, doc, { disableBc: true });
  provider.awareness.setLocalStateField("user", { name, color: colorOf(name), colorLight: colorOf(name) + "33" });
  const update = () => {
    const peers: Peer[] = [];
    provider.awareness.getStates().forEach((state, id) => {
      if (id === doc.clientID || !state.user) return;
      peers.push({ id, name: state.user.name, color: state.user.color, field: state.field ?? "" });
    });
    presence.peers = peers;
  };
  // присутствие меняется и посреди перерисовки (поле с фокусом удаляется при уходе со страницы): обновляем после неё
  provider.awareness.on("change", () => queueMicrotask(update));
  provider.on("status", (event: { status: string }) => { presence.connected = event.status === "connected"; });
  provider.on("sync", (synced: boolean) => { presence.synced = synced; });
  current = { room, doc, provider };
  presence.me = name;
  presence.epoch++;
}

export function leave(): void {
  if (!current) return;
  current.provider.awareness.setLocalState(null);
  current.provider.destroy();
  current.doc.destroy();
  current = null;
  presence.peers = [];
  presence.connected = false;
  presence.synced = false;
  presence.epoch++;
}

/** Документ текущей комнаты (для редакторов, которые привязывают к нему поля). */
export function roomDoc(): Y.Doc | null {
  return current?.doc ?? null;
}

export function roomAwareness(): WebsocketProvider["awareness"] | null {
  return current?.provider.awareness ?? null;
}

/** Своя правка через API в текущей комнате (её адрес или под ним): остальные на странице перечитают данные (RoomPing). */
// пути, которые ничего не меняют (как SAFE_POST в team.rights) и пульс: о них комнате не сообщается
const QUIET = new Set(["preview", "parse", "format", "check", "outline", "build", "resolve", "generate", "randomart", "week", "lock"]);

export function touched(path: string): void {
  if (!current || !(path === current.room || path.startsWith(current.room + "/"))) return;
  if (QUIET.has(path.split("/").pop() ?? "")) return;
  current.doc.getMap("pings").set("writes", Date.now());
}

/** Сообщить остальным, в каком поле фокус автора (пусто: ни в каком). */
export function focusField(field: string): void {
  const room = current;
  queueMicrotask(() => { if (room && room === current) room.provider.awareness.setLocalStateField("field", field); });
}
