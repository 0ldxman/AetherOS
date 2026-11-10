"""Совместная правка в Студии: комнаты Yjs по сущностям, присутствие участников и общий черновик.

Комната называется путём API сущности, как в ленте и обсуждениях (machines/3, items/7). У комнаты на сервере один документ
Yjs (pycrdt) и одно присутствие (Awareness): клиенты (y-websocket во фронте) синхронизируются с документом сервера, сервер
пересылает их правки и присутствие остальным участникам. Документ хранится в базе черновиком (Draft); карта _meta в нём
по каждой форме комнаты (области: main, account:4) говорит, есть ли несохранённое и кто правил (её ведут редакторы фронта,
«Сохранить» снимает флажок).

Войти в комнату можно с правом «смотреть» на раздел сущности, менять документ только с правом «править»: правки того, кто
только смотрит, сервер отбрасывает. Комнаты живут в памяти процесса: совместная правка работает в одном процессе ASGI.
"""
import asyncio

from asgiref.sync import sync_to_async
from pycrdt import Awareness, Doc, Map, YMessageType, YSyncMessageType, create_sync_message, create_update_message, handle_sync_message, read_message

from team import rights

SAVE_DELAY = 1.0            # секунд тишины перед записью черновика в базу

_rooms = {}


def can_join(user, room):
    rule = rights.rule_for(room, "GET")
    return rule is not None and rights.refusal(user, rule) == ""


def can_write(user, room):
    rule = rights.rule_for(room, "PUT")
    return rule is not None and rights.LEVELS.index(rights.level_of(user, rule.section)) >= rights.LEVELS.index(rights.EDIT)


def meta_of(doc):
    """Есть ли в черновике несохранённое хоть в одной форме комнаты и кто правил (без повторов)."""
    meta = doc.get("_meta", type=Map)
    dirty, editors = False, []
    for mark in meta.values():
        if isinstance(mark, dict) and mark.get("dirty"):
            dirty = True
            editors += [name for name in mark.get("editors") or [] if name not in editors]
    return {"dirty": dirty, "editors": editors}


def _load(room):
    from team.models import Draft

    found = Draft.objects.filter(room=room).first()
    return bytes(found.state) if found is not None else None


def _store(room, state, meta):
    from team.models import Draft

    Draft.objects.update_or_create(room=room, defaults={"state": state, "dirty": meta["dirty"], "editors": meta["editors"]})


def _drop(room):
    from team.models import Draft

    Draft.objects.filter(room=room).delete()


class Room:
    def __init__(self, name):
        self.name = name
        self.doc = Doc()
        self.awareness = Awareness(self.doc)
        self.peers = {}                     # участник (потребитель) -> его id клиентов в присутствии
        self._save = None

    async def open(self):
        state = await sync_to_async(_load)(self.name)
        if state:
            self.doc.apply_update(state)

    def people(self):
        """Кто в комнате: имена по порядку входа, без повторов."""
        return list(dict.fromkeys(peer.user.get_username() for peer in self.peers))

    async def join(self, peer):
        self.peers[peer] = set()
        await peer.send_bytes(create_sync_message(self.doc))
        ids = list(self.awareness.states)
        if ids:
            await peer.send_bytes(_awareness_message(self.awareness.encode_awareness_update(ids)))

    async def leave(self, peer):
        ids = list(self.peers.pop(peer, set()))
        if ids:
            self.awareness.remove_awareness_states(ids, peer)
            await self.broadcast(_awareness_message(self.awareness.encode_awareness_update(ids)), skip=peer)
        if not self.peers:
            await self.flush()
            _rooms.pop(self.name, None)

    async def receive(self, peer, data):
        if not data:
            return
        if data[0] == YMessageType.SYNC:
            kind = data[1] if len(data) > 1 else None
            if kind != YSyncMessageType.SYNC_STEP1 and not peer.writer:
                return                                                  # только смотрит: правки не принимаются
            before = self.doc.get_state()
            reply = handle_sync_message(data[1:], self.doc)
            if reply is not None:
                await peer.send_bytes(reply)
            if kind != YSyncMessageType.SYNC_STEP1 and self.doc.get_state() != before:
                await self.broadcast(create_update_message(read_message(data[2:])), skip=peer)
                self.schedule()
        elif data[0] == YMessageType.AWARENESS:
            update = read_message(data[1:])
            known = set(self.awareness.states)
            self.awareness.apply_awareness_update(update, peer)
            self.peers.get(peer, set()).update(set(self.awareness.states) - known)
            await self.broadcast(data, skip=peer)

    async def broadcast(self, message, skip=None):
        for peer in list(self.peers):
            if peer is not skip:
                await peer.send_bytes(message)

    def schedule(self):
        if self._save is not None:
            self._save.cancel()
        self._save = asyncio.ensure_future(self._later())

    async def _later(self):
        try:
            await asyncio.sleep(SAVE_DELAY)
        except asyncio.CancelledError:
            return
        await self.flush()

    async def flush(self):
        """Записать черновик: с несохранённым хранится, без него (всё сохранено или ничего не меняли) удаляется."""
        if self._save is not None and self._save is not asyncio.current_task():
            self._save.cancel()
        self._save = None
        meta = meta_of(self.doc)
        if meta["dirty"]:
            await sync_to_async(_store)(self.name, self.doc.get_update(), meta)
        elif not self.peers:
            await sync_to_async(_drop)(self.name)
        else:
            await sync_to_async(_store)(self.name, self.doc.get_update(), meta)


def _awareness_message(update):
    from pycrdt import write_var_uint

    return bytes([YMessageType.AWARENESS]) + write_var_uint(len(update)) + update


async def room(name):
    found = _rooms.get(name)
    if found is None:
        found = _rooms[name] = Room(name)
        await found.open()
    return found


def live():
    """Комнаты, в которых сейчас кто-то есть: {комната: [имена]}."""
    return {name: found.people() for name, found in _rooms.items() if found.peers}
