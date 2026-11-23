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
    out = {"nodes": out_nodes, "wires": wires}
    groups = doc.get("groups") or {}
    if not isinstance(groups, dict):
        raise ValueError("группы должны быть объектом")
    if groups:
        out["groups"] = {}
        for gid, part in groups.items():
            gid = str(gid).strip()[:32]
            if not gid or not isinstance(part, dict):
                raise ValueError("неверная группа")
            inner = clean({"nodes": part.get("nodes") or [], "wires": part.get("wires") or []})
            out["groups"][gid] = {"title": str(part.get("title") or "")[:120], **inner}
    return out




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
    return kind is not None and (kind.name in ("wait", "wait_cond") or (kind.group in N.NOUNS and node_id in doc.fed))


def _iface_of(node, groups, add, key):
    """Интерфейс обёртки (группы или сценария) или None с проблемой."""
    from graph.runtime import _load, iface

    data = node.get("data") or {}
    if node.get("type") == "group":
        inner = groups.get(str(data.get("group") or ""))
        if inner is None:
            add(key, "нет определения группы")
            return None
        return iface(inner)
    other = _load(data.get("graph"))
    if other is None:
        if data.get("graph"):
            add(key, f"нет сценария «{data.get('graph')}»")
        return None
    return iface(other.doc)


def _part(part, groups, prefix, add, slug, names=()):
    """Проверка одного уровня: самого графа или определения группы (ключ ноды — prefix + id)."""
    from engine import actions as engine
    from graph.runtime import _load

    doc = Doc(part)
    ifaces = {}
    for node_id, node in doc.nodes.items():
        key = prefix + node_id
        kind = N.KINDS.get(node.get("type"))
        if kind is None:
            add(key, f"неизвестная нода «{node.get('type')}»")
            continue
        data = node.get("data") or {}
        if kind.name in N.BOXES:
            ifaces[node_id] = _iface_of(node, groups, add, key)
            if kind.name == "scenario" and data.get("graph") and data.get("graph") == slug:
                add(key, "сценарий не может включать сам себя")
        if kind.name == N.USED_OFFER:
            from graph import offers

            ifaces[node_id] = offers.used_iface(doc, node_id, slug)
        if kind.name == "act:offer" and (node_id, "in") in doc.refs:
            from graph import offers

            if data.get("state") == "hidden":
                add(key, "«Скрыть» — только по событию: без условия возможность и так скрыта")
            elif (node_id, "offer") not in doc.refs and any(":" in one and one.partition(":")[0] != slug for one in offers._keys(data.get("offer"))):
                add(key, "по условию открываются только возможности этого сценария")
        if kind.owned:
            from graph import owned

            thing = owned.thing_of(doc, node_id)
            ifaces[node_id] = owned.iface(owned.owner_of(kind.owned, thing) if thing else None)
            if not thing and (node_id, kind.fields[0].name) in doc.refs:
                add(key, f"«{kind.fields[0].label}» должна быть выбрана заранее: на ноде или на ноде сущности")
        for item in kind.fields:
            fed = (node_id, item.name) in doc.refs
            if item.required and not fed and data.get(item.name) in (None, "") and N.active(kind, data, item.name):
                add(key, f"не заполнено «{item.label}»")
            if kind.name == "thing.find" and item.name == "expr" and data.get(item.name) and not fed:
                from engine import search

                try:
                    search.parse(data[item.name], data.get("what") or "account")
                except search.SearchError as error:
                    add(key, f"условие: {error}")
            if item.kind == "condition" and data.get(item.name):
                try:
                    parse_condition(data[item.name])
                except ValueError as error:
                    add(key, f"условие: {error}")
            if item.kind == "datetime" and data.get(item.name) and not fed:
                from graph import times

                if times.parse(data[item.name]) is None and (kind.name not in ("wait", "time.get") or times.clock(data[item.name]) is None):
                    add(key, f"«{item.label}»: нужно ГГГГ-ММ-ДД ЧЧ:ММ" + (" или ЧЧ:ММ" if kind.name in ("wait", "time.get") else ""))
            if item.kind == "clock" and data.get(item.name):
                try:
                    _clock(data[item.name])
                except ValueError as error:
                    add(key, str(error))
        if kind.name == "wait":
            mode = data.get("mode") or "delay"
            if mode == "until" and not data.get("at") and (node_id, "at") not in doc.refs:
                add(key, "нужно время ЧЧ:ММ или дата")
            if mode == "delay" and not any(data.get(name) or (node_id, name) in doc.refs for name in N.WAIT_UNITS):
                add(key, "не задано, сколько ждать", WARNING)
        if kind.name == "launch" and data.get("graph"):
            other = _load(data.get("graph"))
            if other is None:
                add(key, f"нет сценария «{data.get('graph')}»")
            elif not any((n or {}).get("type") == "group_in" for n in (other.doc or {}).get("nodes") or []):
                add(key, f"у сценария «{other.slug}» нет ноды «Вход»: запускать некуда")
        if kind.name in ("group_in", "group_out"):
            names = [name for name, _ in N.named(data)]
            if len(names) != len(set(names)):
                add(key, "повторяются имена сокетов")
            if [n for n in doc.nodes.values() if n.get("type") == kind.name].__len__() > 1:
                add(key, f"на уровне больше одной ноды «{kind.label}»: работает первая", WARNING)
        if kind.group in N.NOUNS:
            if node_id in doc.fed and kind.start_only:
                add(key, f"«{kind.label}» бывает только стартом: уберите входящий провод")
            as_ref = any(src[0] == node_id for src in doc.refs.values()) or any(
                src == node_id and N.out_type(kind, out) != N.EVENT for (src, out) in doc.flow)
            if not [out for out in doc.wired(node_id) if out in kind.events or (kind.name == N.USED_OFFER and N.event_of(kind, out))] and not as_ref:
                add(key, "ни один выход не подключён: нода ничего не ловит", WARNING)
        if kind.group == N.ACTION and (kind.spec is not None or kind.variants) and not any(k[0] == node_id for k in doc.refs):
            _, action = N.action_of(kind, data)
            for text in engine.check([action], provides=("world", "user", "account")):
                add(key, text.split(": ", 1)[-1])
        if kind.name == "branch_gate" and (node_id, "branches") not in doc.refs:
            title = str(data.get("name") or "").strip()
            if not title:
                add(key, "укажите «Название ветвления» или подключите провод «Ветвление»")
            elif title not in names:
                add(key, f"нет ветвления с названием «{title}»")
        if kind.name == "branching":
            types = {(n or {}).get("type") for n in ((groups.get(str(data.get("group") or "")) or {}).get("nodes") or [])}
            if "branch_head" not in types:
                add(key, "внутри нет «Начала ветки»")
            elif data.get("repeat") == "yes" and "branch_owner" not in types:
                add(key, "«Повторять» без «Ветка: Назначить владельца»: занятая ветка так и останется ничьей", WARNING)
        if kind.name == "join":                              # последний вход — запасной (растёт сам), его не проверяем
            for sock in N.sockets(kind, data, "in")[:-1]:
                if not any(dst == node_id and inp == sock for targets in doc.flow.values() for dst, inp in targets):
                    add(key, f"вход {sock[1:]} не подключён", WARNING)

    for wire in (part or {}).get("wires") or []:
        src, out_name, dst, inp = (str(wire.get(name)) for name in ("from", "out", "to", "in"))
        src_kind, dst_kind = doc.kind(src), doc.kind(dst)
        if src_kind is None or dst_kind is None:
            add(prefix + (src if src_kind else dst), "провод к несуществующей ноде")
            continue
        if out_name not in N.sockets(src_kind, doc.data(src), "out", ifaces.get(src)):
            if ifaces.get(src, True) is not None:
                add(prefix + src, f"нет выхода «{out_name}»")
            continue
        src_type = N.sock_type(src_kind, doc.data(src), "out", out_name, ifaces.get(src))
        if inp.startswith("f:"):
            dst_type = N.sock_type(dst_kind, doc.data(dst), "in", inp)
            label = N.input_label(dst_kind, doc.data(dst), inp[2:])
            if not dst_type:
                add(prefix + dst, f"у «{dst_kind.label}» нет входа «{label}»")
            elif not N.compatible(src_type, dst_type):
                add(prefix + dst, f"«{label}» ждёт {N.type_label(dst_type)}, а приходит {N.type_label(src_type)}")
            continue
        if inp not in N.sockets(dst_kind, doc.data(dst), "in", ifaces.get(dst)):
            if ifaces.get(dst, True) is not None:
                add(prefix + dst, f"нет входа «{inp}»")
            continue
        dst_type = N.sock_type(dst_kind, doc.data(dst), "in", inp, ifaces.get(dst))
        if not N.compatible(src_type, dst_type):
            add(prefix + dst, f"вход ждёт {N.type_label(dst_type)}, а приходит {N.type_label(src_type)}")
        if out_name == N.TIMEOUT and src_kind.group in N.NOUNS and src not in doc.fed:
            add(prefix + src, "таймаут бывает только у ждущей ноды (со входом)")


def _owned_rules(raw, add):
    """Граф попытки решает сразу: ожиданий в нём нет."""
    doc = Doc(raw)
    for node_id, node in doc.nodes.items():
        kind = N.KINDS.get(node.get("type"))
        if kind is not None and (kind.name in ("wait", "wait_cond") or (kind.group in N.NOUNS and not kind.name.startswith("attempt:"))):
            add(node_id, "в графе попытки нельзя ждать: решение принимается сразу")
    if not any(str(n.get("type") or "").startswith("attempt:") for n in doc.nodes.values()):
        add("", "нет стартовой ноды «Попытка»")


def _variables(raw, groups, add):
    """Переменная сценария читается («Переменная: Значение», «var:имя» в условии), а нигде не записывается: чаще всего опечатка в имени."""
    import re

    written, read = set(), []
    for prefix, part in [("", raw), *[(f"{gid}::", part) for gid, part in groups.items()]]:
        for node in (part or {}).get("nodes") or []:
            if not isinstance(node, dict):
                continue
            data = node.get("data") or {}
            key = f"{prefix}{node.get('id')}"
            names = [str(row.get("name") or "").strip() for row in data.get("rows") or [] if isinstance(row, dict)]
            if node.get("type") == "var_set" and (data.get("mode") or "set") in ("set", "op"):
                written.update(name for name in names if name)
            elif node.get("type") in ("ctl_switch", "ctl_text", "ctl_choice", "ctl_number") and str(data.get("name") or "").strip():
                written.add(str(data["name"]).strip())                       # значение управления — переменная сценария
            elif node.get("type") == "var_get":
                read += [(key, name) for name in names if name]
            for value in data.values():
                if isinstance(value, str) and "var:" in value:
                    read += [(key, found.strip()) for found in re.findall(r"var:([^\s()<>=]+)", value)]
    for key, name in read:
        if not any(name == w or w.startswith(name + ".") or name.startswith(w + ".") for w in written):
            add(key, f"переменная «{name}» читается, но нигде не записывается", WARNING)


def problems(raw, slug="", owner=""):
    """Список проблем сценария. Ключ ноды: её id на уровне графа или «группа::id» внутри определения группы."""
    from graph.runtime import flatten

    raw = raw or {}
    groups = raw.get("groups") or {}
    out = []

    def add(node, text, level=ERROR):
        found = {"node": node, "text": text, "level": level}
        if found not in out:                     # одно и то же видят проверка полей и проверка действия движка — показать раз
            out.append(found)

    names = {str(((n or {}).get("data") or {}).get("name") or "").strip() for level in [raw, *groups.values()] for n in (level or {}).get("nodes") or []
             if isinstance(n, dict) and n.get("type") == "branching"} - {""}
    _part(raw, groups, "", add, slug, names)
    if owner:
        _owned_rules(raw, add)
    for gid, part in groups.items():
        _part(part, groups, f"{gid}::", add, slug, names)
    _variables(raw, groups, add)
    flat = Doc(flatten(raw, slug))
    if flat.nodes and not owner and not any(flat.is_start(node_id) and flat.wired(node_id) for node_id in flat.nodes):
        has_entry = any(node.get("type") == "group_in" for node in raw.get("nodes") or [])
        if not has_entry:
            add("", "нет старта: существительное без входящего провода и с подключённым выходом", WARNING)
    for group in _cycles(flat):
        if not any(_waits(flat, node_id) for node_id in group):
            first = sorted(group)[0]
            add(first if "/" not in first else first.split("/")[0], "цикл без ожидания: ход остановится на лимите")
    return out


ERRORS_TTL = 30          # секунды: карточки сценариев опрашиваются часто, а ссылки на ключи и вложенные графы меняются редко


def error_count(graph):
    """Сколько ошибок у сценария (для карточки). Кэш по версии графа: новая правка — пересчёт сразу, внешние причины — за ERRORS_TTL."""
    from django.core.cache import cache

    key = f"graph:errors:{graph.pk}:{graph.updated_at.timestamp() if graph.updated_at else 0}"
    found = cache.get(key)
    if found is None:
        found = sum(1 for p in problems(graph.doc, graph.slug, graph.owner) if p["level"] == "error")
        cache.set(key, found, ERRORS_TTL)
    return found
