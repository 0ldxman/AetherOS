"""Проверка сценария для Студии: что не так с нодами и проводами. Каждая проблема — {"node", "text", "level"}: error (так
работать не будет) или warning (будет, но, похоже, не так, как задумано)."""
from graph import nodes as N
from graph.runtime import Doc, parse_condition, _clock

ERROR, WARNING = "error", "warning"


def clean(doc):
    """Документ в каноническом виде: только известные поля, id строками. Неверное — ValueError."""
    if not isinstance(doc, dict):
        raise ValueError("граф должен быть объектом")
    out_nodes, ids = [], set()
    for node in doc.get("nodes") or []:
        if not isinstance(node, dict):
            raise ValueError("нода должна быть объектом")
        node_id = str(node.get("id") or "").strip()[:32]
        if not node_id or node_id in ids:
            raise ValueError(f"повтор или пустой id ноды «{node_id}»")
        ids.add(node_id)
        item = {"id": node_id, "type": str(node.get("type") or "")[:40], "x": float(node.get("x") or 0), "y": float(node.get("y") or 0),
                "data": node.get("data") if isinstance(node.get("data"), dict) else {}}
        for extra in ("w", "h"):
            if node.get(extra) is not None:
                item[extra] = float(node[extra])
        for flag in ("mute", "collapsed"):
            if node.get(flag):
                item[flag] = True
        out_nodes.append(item)
    wires, seen = [], set()
    for wire in doc.get("wires") or []:
        if not isinstance(wire, dict):
            raise ValueError("провод должен быть объектом")
        key = tuple(str(wire.get(name) or "")[:40] for name in ("from", "out", "to", "in"))
        if key in seen or not all(key):
            continue
        seen.add(key)
        wires.append({"id": str(wire.get("id") or "-".join(key))[:120], "from": key[0], "out": key[1], "to": key[2], "in": key[3]})
    return {"nodes": out_nodes, "wires": wires}


def _cycles(doc):
    """Сильно связные компоненты потока (Тарьян): циклы."""
    graph = {}
    for (src, _), targets in doc.flow.items():
        graph.setdefault(src, set()).update(dst for dst, _ in targets)
    index, low, stack, on, out = {}, {}, [], set(), []
    counter = [0]

    def visit(start):
        work = [(start, iter(graph.get(start, ())))]
        index[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on.add(start)
        while work:
            node, it = work[-1]
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter[0]
                    counter[0] += 1
                    stack.append(nxt)
                    on.add(nxt)
                    work.append((nxt, iter(graph.get(nxt, ()))))
                    break
                if nxt in on:
                    low[node] = min(low[node], index[nxt])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    group = []
                    while True:
                        item = stack.pop()
                        on.discard(item)
                        group.append(item)
                        if item == node:
                            break
                    if len(group) > 1 or node in graph.get(node, ()):
                        out.append(group)

    for node in list(graph):
        if node not in index:
            visit(node)
    return out


def _waits(doc, node_id):
    kind = doc.kind(node_id)
    return kind is not None and (kind.name == "wait" or (kind.group == N.NOUN and node_id in doc.fed))


def problems(raw):
    """Список проблем сценария."""
    from engine import actions as engine

    doc = Doc(raw)
    out = []

    def add(node, text, level=ERROR):
        out.append({"node": node, "text": text, "level": level})

    for node_id, node in doc.nodes.items():
        kind = N.KINDS.get(node.get("type"))
        if kind is None:
            add(node_id, f"неизвестная нода «{node.get('type')}»")
            continue
        data = node.get("data") or {}
        for item in kind.fields:
            fed = (node_id, item.name) in doc.refs
            if item.required and not fed and data.get(item.name) in (None, ""):
                add(node_id, f"не заполнено «{item.label}»")
            if item.kind == "condition" and data.get(item.name):
                try:
                    parse_condition(data[item.name])
                except ValueError as error:
                    add(node_id, f"условие: {error}")
            if item.kind == "clock" and data.get(item.name):
                try:
                    _clock(data[item.name])
                except ValueError as error:
                    add(node_id, str(error))
        if kind.name == "file" and not (data.get("item") or data.get("path")):
            add(node_id, "нужен объект или путь")
        if kind.name == "wait":
            mode = data.get("mode") or "delay"
            if mode == "condition" and not data.get("condition"):
                add(node_id, "нужно условие")
            if mode == "until" and not data.get("at"):
                add(node_id, "нужно время ЧЧ:ММ")
        if kind.name == "time" and (data.get("mode") == "once") and not data.get("date"):
            add(node_id, "нужна дата для «один раз»")
        if kind.name == "choose":
            for number, row in enumerate(data.get("rows") or [], 1):
                try:
                    parse_condition((row or {}).get("condition"))
                except ValueError as error:
                    add(node_id, f"строка {number}: {error}")
        if kind.group == N.NOUN:
            if node_id in doc.fed and kind.start_only:
                add(node_id, f"«{kind.label}» бывает только стартом: уберите входящий провод")
            as_ref = any(src == node_id for src in doc.refs.values())
            if not [out for out in doc.wired(node_id) if out in kind.events] and not as_ref:
                add(node_id, "ни один выход не подключён: нода ничего не ловит", WARNING)
        if kind.group == N.ACTION and not any(key[0] == node_id for key in doc.refs):
            action = {"do": kind.spec.name, **{key: value for key, value in data.items() if value not in (None, "")}}
            for text in engine.check([action], provides=("world", "user", "account")):
                add(node_id, text.split(": ", 1)[-1])
        ins = N.sockets(kind, data, "in")
        if kind.name in ("all", "race"):
            for sock in ins:
                if not any(dst == node_id and inp == sock for targets in doc.flow.values() for dst, inp in targets):
                    add(node_id, f"вход {sock[1:]} не подключён", WARNING)

    for wire in (raw or {}).get("wires") or []:
        src, out_name, dst, inp = (str(wire.get(name)) for name in ("from", "out", "to", "in"))
        src_kind, dst_kind = doc.kind(src), doc.kind(dst)
        if src_kind is None or dst_kind is None:
            add(src if src_kind else dst, "провод к несуществующей ноде")
            continue
        if out_name not in N.sockets(src_kind, doc.data(src), "out"):
            add(src, f"нет выхода «{out_name}»")
            continue
        if inp.startswith("f:"):
            field = next((f for f in dst_kind.fields if f.name == inp[2:]), None)
            if out_name != N.REF or field is None or N.REF_KINDS.get(field.kind) != (src_kind.ref[0] if src_kind.ref else None):
                add(dst, f"«{src_kind.label}» не подходит в поле «{field.label if field else inp[2:]}»")
            continue
        if out_name == N.REF:
            add(src, "выход-ссылку можно вести только в поле действия")
            continue
        if inp not in N.sockets(dst_kind, doc.data(dst), "in"):
            add(dst, f"нет входа «{inp}»")
        if out_name == N.TIMEOUT and src_kind.group == N.NOUN and src not in doc.fed:
            add(src, "таймаут бывает только у ждущей ноды (со входом)")

    if doc.nodes and not any(doc.is_start(node_id) and doc.wired(node_id) for node_id in doc.nodes):
        add("", "нет старта: существительное без входящего провода и с подключённым выходом", WARNING)
    for group in _cycles(doc):
        if not any(_waits(doc, node_id) for node_id in group):
            add(sorted(group)[0], "цикл без ожидания: прохождение остановится на лимите")
    return out
