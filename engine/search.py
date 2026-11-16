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
GROUP = re.compile(r"^group:account:([\w.-]+)$")                      # учётка в группе прав
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b, "=": lambda a, b: a == b}


class SearchError(ValueError):
    pass


def tidy(text):
    """count:x >= 5 -> count:x>=5: пробелы вокруг сравнения допустимы."""
    return SPACED.sub(r"\1", str(text or "").strip())


def own_atom(text, owner):
    """(вид tag|count|group, имя, для игрока, оператор, число), если атом — про кандидата вида owner; иначе None."""
    group = GROUP.match(str(text or "").strip())
    if group:
        return ("group", group[1].lower(), False, None, None) if owner == "account" else None
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
        raise SearchError(f"нет условия на саму вещь: нужен tag:{owner}:имя или count:{owner}:имя"
                          + (" или group:account:группа" if owner == "account" else "") + " (tag:world:… сам по себе не отбирает)")
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


ORDERS = ("name", "count", "tag_time", "changed", "random")


def find(text, what, user=None, facts_of_player=frozenset(), among=None, order="name", by="", descending=False, limit=None):
    """Ключи вещей вида what, для которых условие верно, по порядку: name — по имени, count — по счётчику by, tag_time — когда поставили
    тег by, changed — когда последний раз меняли тег или счётчик by (у кого нет — в конце), random — случайно. by — имя или имя@player.
    limit — сколько взять."""
    import random

    from secure.access import satisfied

    req = parse(text, what)
    owner = OWNER_OF[what]
    universe = _universe(owner, among)
    names = {own_atom(atom, owner)[1] for atom in _atoms(req) if own_atom(atom, owner) and own_atom(atom, owner)[0] != "group"}
    groups = {}
    if owner == "account" and any((own_atom(atom, owner) or ("",))[0] == "group" for atom in _atoms(req)):
        from machines.models import MachineProfile

        groups = {pk: {str(name).lower() for name in (found or [])}
                  for pk, found in MachineProfile.objects.filter(pk__in=list(universe)).values_list("pk", "groups")}
    order = order if order in ORDERS else "name"
    sort_name, _, sort_per = str(by or "").strip().lower().partition("@")
    if order in ("count", "tag_time", "changed") and sort_name:
        names.add(sort_name)
    known, when = {}, {}
    from engine.models import Value
    from django.db.models import Q

    rows = Value.objects.filter(owner=owner, owner_id__in=list(universe), name__in=names)
    rows = rows.filter(Q(user__isnull=True) | Q(user=user)) if user is not None else rows.filter(user__isnull=True)
    for row in rows.values_list("kind", "owner_id", "name", "user_id", "value", "changed_at"):
        known[(row[0], row[1], row[2], row[3] is not None)] = row[4]
        when[(row[0], row[1], row[2], row[3] is not None)] = row[5]
    shared = {}

    def holds(node, pk):
        if isinstance(node, str):
            mine = own_atom(node, owner)
            if mine is None:
                if node not in shared:
                    shared[node] = bool(satisfied(node, facts_of_player))
                return shared[node]
            kind, name, per, op, number = mine
            if kind == "group":
                return name in groups.get(pk, set())
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

    found = sorted((pk for pk in universe if holds(req, pk)), key=lambda pk: str(universe[pk]).lower())
    per = sort_per == "player"
    if order == "random":
        random.shuffle(found)
    elif order == "count" and sort_name:
        found.sort(key=lambda pk: known.get((values.COUNT, pk, sort_name, per), 0), reverse=descending)
    elif order in ("tag_time", "changed") and sort_name:
        def moment(pk):
            if order == "tag_time":
                return when.get((values.TAG, pk, sort_name, per)) if known.get((values.TAG, pk, sort_name, per)) else None
            stamps = [when.get((kind, pk, sort_name, per)) for kind in (values.TAG, values.COUNT)]
            stamps = [stamp for stamp in stamps if stamp is not None]
            return max(stamps) if stamps else None

        dated = [pk for pk in found if moment(pk) is not None]
        dated.sort(key=moment, reverse=descending)
        found = dated + [pk for pk in found if moment(pk) is None]          # без отметки — в конце
    elif order == "name" and descending:
        found.reverse()
    if limit:
        found = found[:limit]
    return [universe[pk] for pk in found]
