"""Перевод сохранённых графов на новые ноды (вызывается миграциями): старые документы продолжают работать без правки руками."""

STATE = ("lag_ms", "noise_pct", "drop_pct", "bandwidth_kbps", "input_noise_pct", "overload_pct", "screen_noise")
ACCESS = ("groups", "endpoints", "root", "blocked")
# выход сущности, ушедший в атрибут: (вид сущности, выходы) -> (вид атрибута, его поле-вход)
MOVED = {("ent:machine", STATE): ("attr:machine.state", "machine"), ("ent:account", ACCESS): ("attr:account.access", "account")}
ATTR_DX = 280                           # атрибут встаёт правее своей сущности


def _moved(kind, out):
    return next((found for (name, outs), found in MOVED.items() if name == kind and out in outs), None)


def _level(level):
    """Один уровень документа (сам граф или группа). True — что-то поменялось."""
    nodes = [node for node in level.get("nodes") or [] if isinstance(node, dict) and node.get("id")]
    by_id = {str(node["id"]): node for node in nodes}
    changed = False
    for node in nodes:                                   # «Машина: Изменить» с дефектом — «Машина: Изменить состояние»
        data = node.get("data") or {}
        if node.get("type") == "act:machine.change" and data.get("variant") in STATE:
            what = data["variant"]
            node["type"] = "act:machine.state"
            node["data"] = {"mode": "set", "machine": data.get("machine"), what: data.get(what) if data.get(what) is not None else "0"}
            changed = True
    made = {}
    for wire in list(level.get("wires") or []):        # провода со старых выходов сущности — из атрибута рядом с ней
        if not isinstance(wire, dict):
            continue
        src = by_id.get(str(wire.get("from")))
        found = _moved(src.get("type"), wire.get("out")) if src else None
        if found is None:
            continue
        attr, field = found
        key = (str(src["id"]), attr)
        if key not in made:
            new_id = f"{src['id']}-{attr.split(':')[1].replace('.', '-')}"
            while new_id in by_id:
                new_id += "x"
            node = {"id": new_id, "type": attr, "x": (src.get("x") or 0) + ATTR_DX, "y": src.get("y") or 0, "data": {}}
            level.setdefault("nodes", []).append(node)
            by_id[new_id] = node
            level.setdefault("wires", []).append({"id": f"w-{new_id}", "from": src["id"], "out": "value", "to": new_id, "in": f"f:{field}"})
            made[key] = new_id
        wire["from"] = made[key]
        changed = True
    return changed


_WROTE = {"mail": "from_address", "forum": "nick", "air": "callsign"}


def _wrote_level(level):
    """«Персонаж: Получил сообщение» с выбранным каналом: «От кого» стал адресом, ником или позывным; темы у эфира нет."""
    channels = {str(node["id"]): (node.get("data") or {}).get("channel") or "any" for node in level.get("nodes") or []
                if isinstance(node, dict) and node.get("type") == "on:character.wrote"}
    changed = False
    for wire in list(level.get("wires") or []):
        channel = channels.get(str(wire.get("from"))) if isinstance(wire, dict) else None
        if channel in _WROTE and wire.get("out") == "sender":
            wire["out"] = _WROTE[channel]
            changed = True
        elif channel == "air" and wire.get("out") == "subject":
            level["wires"].remove(wire)
            changed = True
    return changed


def wrote_outs(doc):
    """Выходы «Получил сообщение» по каналу. True — граф поменялся."""
    if not isinstance(doc, dict):
        return False
    changed = _wrote_level(doc)
    for group in (doc.get("groups") or {}).values():
        if isinstance(group, dict):
            changed = _wrote_level(group) or changed
    return changed


def _events_level(level):
    """Передачи станций — «Эфир: Передача станции»; «Добавлен» у слоя — «Слой: Добавлен» рядом (с теми же фильтрами и входами)."""
    changed = False
    nodes = [node for node in level.get("nodes") or [] if isinstance(node, dict) and node.get("id")]
    ids = {str(node["id"]) for node in nodes}
    for node in nodes:
        data = node.get("data") or {}
        if node.get("type") == "on:air.sent" and "by" in data:
            node["type"] = "on:air.station" if data.get("by") == "station" else "on:air.sent"
            node["data"] = {key: value for key, value in data.items() if key != "by" and (key != "character" or data.get("by") == "station")}
            changed = True
        if node.get("type") != "on:layer.changed":
            continue
        moved = [wire for wire in level.get("wires") or [] if isinstance(wire, dict) and str(wire.get("from")) == str(node["id"])
                 and wire.get("out") == "added"]
        if not moved:
            continue
        new_id = f"{node['id']}-added"
        while new_id in ids:
            new_id += "x"
        ids.add(new_id)
        level["nodes"].append({"id": new_id, "type": "on:layer.added", "x": node.get("x") or 0, "y": (node.get("y") or 0) + 220,
                               "data": {key: value for key, value in data.items() if key in ("layer", "item", "type", "repeat", "past", "own", "timeout")}})
        for wire in moved:
            wire["from"] = new_id
        for wire in list(level.get("wires") or []):        # ждущая нода: входы те же
            if isinstance(wire, dict) and str(wire.get("to")) == str(node["id"]):
                level["wires"].append({**wire, "id": f"{wire.get('id') or 'w'}-{new_id}", "to": new_id})
        changed = True
    return changed


def events(doc):
    """Триггеры и события разведены: эфир станций и добавленный слой — свои ноды. True — граф поменялся."""
    if not isinstance(doc, dict):
        return False
    changed = _events_level(doc)
    for group in (doc.get("groups") or {}).values():
        if isinstance(group, dict):
            changed = _events_level(group) or changed
    return changed


def _flow_level(level):
    """«Выбор» — цепочка «Направить: Если»: строка за строкой, «Ложь» в следующую, у последней «Ложь» — бывшее «Иначе»."""
    changed = False
    for node in [n for n in level.get("nodes") or [] if isinstance(n, dict) and n.get("type") == "choose"]:
        rows = [row for row in (node.get("data") or {}).get("rows") or [] if isinstance(row, dict)] or [{"condition": ""}]
        nid, wires = str(node["id"]), level.setdefault("wires", [])
        ids = [nid] + [f"{nid}-{n}" for n in range(2, len(rows) + 1)]
        node["type"], node["data"] = "check", {"condition": rows[0].get("condition") or ""}
        for number, row in enumerate(rows[1:], 2):
            level["nodes"].append({"id": ids[number - 1], "type": "check", "x": (node.get("x") or 0) + 280 * (number - 1), "y": node.get("y") or 0,
                                   "data": {"condition": row.get("condition") or ""}})
        for number in range(1, len(rows)):
            wires.append({"id": f"w-{ids[number - 1]}-no", "from": ids[number - 1], "out": "no", "to": ids[number], "in": "in"})
        for wire in wires:
            if not isinstance(wire, dict) or str(wire.get("from")) != nid:
                continue
            out = str(wire.get("out") or "")
            if out.startswith("r") and out[1:].isdigit() and 1 <= int(out[1:]) <= len(rows):
                wire["from"], wire["out"] = ids[int(out[1:]) - 1], "yes"
            elif out == "else":
                wire["from"], wire["out"] = ids[-1], "no"
        changed = True
    return changed


def flow_nodes(doc):
    """Ноды потока: «Выбор» стал цепочкой «Если». True — граф поменялся."""
    if not isinstance(doc, dict):
        return False
    changed = _flow_level(doc)
    for group in (doc.get("groups") or {}).values():
        if isinstance(group, dict):
            changed = _flow_level(group) or changed
    return changed


def _each_level(level, groups):
    """Старое «Для каждого» без веток стало группой: внутри «Начало ветки» → «Конец ветки». С ветками — остаётся старым (работает как было)."""
    changed = False
    for node in [n for n in level.get("nodes") or [] if isinstance(n, dict) and n.get("type") == "foreach"]:
        if any(isinstance(w, dict) and str(w.get("from")) == str(node["id"]) for w in level.get("wires") or []):
            continue
        key = 1
        while f"each{key}" in groups:
            key += 1
        group = f"each{key}"
        groups[group] = {"title": "Для каждого", "nodes": [{"id": "start", "type": "branch_in", "x": 0, "y": 0, "data": {}},
                                                          {"id": "end", "type": "branch_out", "x": 520, "y": 0, "data": {}}],
                         "wires": [{"id": "w-start-end", "from": "start", "out": "next", "to": "end", "in": "in"}]}
        node["type"], node["data"] = "each", {**(node.get("data") or {}), "group": group}
        changed = True
    return changed


def each_boxes(doc):
    """«Для каждого» — группа через Tab. True — граф поменялся."""
    if not isinstance(doc, dict):
        return False
    groups = doc.setdefault("groups", {})
    changed = False
    for level in [doc, *[g for g in list(groups.values()) if isinstance(g, dict)]]:
        changed = _each_level(level, groups) or changed
    if not groups:
        doc.pop("groups")
    return changed


def attributes(doc):
    """Состояние машины и доступ учётки ушли в атрибуты, дефекты из «Машина: Изменить» — в «Изменить состояние». True — граф поменялся."""
    if not isinstance(doc, dict):
        return False
    changed = _level(doc)
    for group in (doc.get("groups") or {}).values():
        if isinstance(group, dict):
            changed = _level(group) or changed
    return changed
