"""Поиск вещей по условию на теги и счётчики (нода «Найти по условию»).

Условие — тот же язык, что у условий доступа: and, or, not, скобки, tag:…, count:…[оп число], world:…. Атом с видом вещи, но без самой
вещи — tag:account:имя, count:machine:имя>=3, tag:account:имя@player — проверяется у каждого кандидата этого вида; остальные атомы
(tag:world:alarm, tag:имя игрока хода, tag:machine:core:имя) одинаковы для всех кандидатов и только сужают или открывают весь поиск.
Поэтому в условии должен быть хотя бы один атом кандидата: иначе это не фильтр.
"""
import re

from engine import facts, values

OWNER_OF = {"player": "player", "character": "character", "machine": "machine", "account": "account", "server": "server", "item": "object"}
SPACED = re.compile(r"\s*(>=|<=|>|<|=)\s*")
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b, "=": lambda a, b: a == b}


class SearchError(ValueError):
    pass


def tidy(text):
    """count:x >= 5 -> count:x>=5: пробелы вокруг сравнения допустимы."""
    return SPACED.sub(r"\1", str(text or "").strip())


def own_atom(text, owner):
    """(вид tag|count, имя, для игрока, оператор, число), если атом — про кандидата вида owner; иначе None."""
    match = facts.ATOM.fullmatch(str(text or "").strip())
    if not match:
        return None
    kind, rest, op, number = match.groups()
    head, sep, name = rest.partition(":")
    if not sep or head != owner or ":" in name or not name:
        return None
    per = name.endswith(facts.PLAYER)
    name = name[:-len(facts.PLAYER)] if per else name
    if not name or (kind == "tag" and op):
        return None
    return kind, name.lower(), per, op, int(number) if number is not None else None


def _atoms(req):
    if isinstance(req, str):
        yield req
    elif isinstance(req, dict):
        for value in req.values():
            for item in value if isinstance(value, list) else [value]:
                yield from _atoms(item)


def parse(text, what):
    """Условие поиска вещей вида what (тип провода: account, machine, item…): структура или SearchError."""
    from graph.runtime import parse_condition

    owner = OWNER_OF.get(what)
    if owner is None:
        raise SearchError(f"нельзя искать «{what}»")
    try:
        req = parse_condition(tidy(text))
    except ValueError as error:
        raise SearchError(str(error)) from None
    if not any(own_atom(atom, owner) for atom in _atoms(req)):
        raise SearchError(f"нет условия на саму вещь: нужен tag:{owner}:имя или count:{owner}:имя (tag:world:… сам по себе не отбирает)")
    return req


def _universe(owner, among):
    """{номер: ключ} кандидатов: все вещи вида или только из списка among."""
    if owner == "account":
        from machines.models import MachineProfile
        from machines.world import edits

        rows = MachineProfile.objects.select_related("machine")
        if among is not None:
            found = [edits.account(key) for key in among]
            rows = [row for row in found if row is not None]
        return {row.pk: edits.account_key(row) for row in rows}
    model, field = values._model(owner)
    rows = model.objects.all()
    if owner == "player":
        rows = rows.filter(sandbox_of__isnull=True)
    if among is not None:
        rows = rows.filter(**{f"{field}__in": [str(key) for key in among]})
    return dict(rows.values_list("pk", field))


def find(text, what, user=None, facts_of_player=frozenset(), among=None, sort="", descending=True, limit=None):
    """Ключи вещей вида what, для которых условие верно. sort — счётчик для порядка (имя или имя@player), limit — сколько взять."""
    from secure.access import satisfied

    req = parse(text, what)
    owner = OWNER_OF[what]
    universe = _universe(owner, among)
    names = {own_atom(atom, owner)[1] for atom in _atoms(req) if own_atom(atom, owner)}
    sort_name, _, sort_per = str(sort or "").strip().lower().partition("@")
    if sort_name:
        names.add(sort_name)
    known = {}
    from engine.models import Value
    from django.db.models import Q

    rows = Value.objects.filter(owner=owner, owner_id__in=list(universe), name__in=names)
    rows = rows.filter(Q(user__isnull=True) | Q(user=user)) if user is not None else rows.filter(user__isnull=True)
    for row in rows.values_list("kind", "owner_id", "name", "user_id", "value"):
        known[(row[0], row[1], row[2], row[3] is not None)] = row[4]
    shared = {}

    def holds(node, pk):
        if isinstance(node, str):
            mine = own_atom(node, owner)
            if mine is None:
                if node not in shared:
                    shared[node] = bool(satisfied(node, facts_of_player))
                return shared[node]
            kind, name, per, op, number = mine
            if per and user is None:
                return False
            value = known.get((values.TAG if kind == "tag" else values.COUNT, pk, name, per), 0)
            if kind == "tag":
                return bool(value)
            return value > 0 if op is None else OPS[op](value, number)
        if "all" in node:
            return all(holds(item, pk) for item in node["all"])
        if "any" in node:
            return any(holds(item, pk) for item in node["any"])
        if "not" in node:
            return not holds(node["not"], pk)
        return False

    found = [pk for pk in universe if holds(req, pk)]
    if sort_name:
        found.sort(key=lambda pk: known.get((values.COUNT, pk, sort_name, sort_per == "player"), 0), reverse=descending)
    else:
        found.sort(key=lambda pk: str(universe[pk]).lower())
    if limit:
        found = found[:limit]
    return [universe[pk] for pk in found]
