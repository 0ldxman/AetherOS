// Совместная правка (team.collab): комната Yjs сущности, на странице которой автор сейчас. Одна комната на страницу:
// присутствие (кто здесь, где его фокус) и общий документ, к которому редакторы привязывают свои поля.
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";

export type Peer = { id: number; name: string; color: string; field: string };

export const presence = $state<{ room: string; peers: Peer[]; connected: boolean }>({ room: "", peers: [], connected: false });

let current: { room: string; doc: Y.Doc; provider: WebsocketProvider } | null = null;

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
  provider.awareness.setLocalStateField("user", { name, color: colorOf(name) });
  const update = () => {
    const peers: Peer[] = [];
    provider.awareness.getStates().forEach((state, id) => {
      if (id === doc.clientID || !state.user) return;
      peers.push({ id, name: state.user.name, color: state.user.color, field: state.field ?? "" });
    });
    presence.peers = peers;
  };
  provider.awareness.on("change", update);
  provider.on("status", (event: { status: string }) => { presence.connected = event.status === "connected"; });
  current = { room, doc, provider };
}

export function leave(): void {
  if (!current) return;
  current.provider.awareness.setLocalState(null);
  current.provider.destroy();
  current.doc.destroy();
  current = null;
  presence.peers = [];
  presence.connected = false;
}

/** Документ текущей комнаты (для редакторов, которые привязывают к нему поля). */
export function roomDoc(): Y.Doc | null {
  return current?.doc ?? null;
}

/** Сообщить остальным, в каком поле фокус автора (пусто: ни в каком). */
export function focusField(field: string): void {
  current?.provider.awareness.setLocalStateField("field", field);
}
