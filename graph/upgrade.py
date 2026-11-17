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


def attributes(doc):
    """Состояние машины и доступ учётки ушли в атрибуты, дефекты из «Машина: Изменить» — в «Изменить состояние». True — граф поменялся."""
    if not isinstance(doc, dict):
        return False
    changed = _level(doc)
    for group in (doc.get("groups") or {}).values():
        if isinstance(group, dict):
            changed = _level(group) or changed
    return changed
