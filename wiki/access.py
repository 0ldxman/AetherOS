from dataclasses import dataclass

from secure.access import satisfied


@dataclass(frozen=True)
class State:
    """Итог проверки: видна ли запись и открыта ли она."""
    visible: bool
    open: bool


def _all_satisfied(conditions, keys):
    # пустое условие satisfied считает открытым, отдельно его обрабатывать не нужно
    return all(satisfied(c, keys) for c in conditions)


def namespace_state(namespace, keys):
    """Состояние неймспейса: условия всей цепочки от корня до него."""
    nodes = namespace.chain()
    return State(
        visible=not any(n.hidden for n in nodes),
        open=_all_satisfied([n.access for n in nodes], keys),
    )


def document_state(doc, keys, via_direct_link=False):
    """Состояние записи: условия неймспейсов цепочки плюс условия самой записи.

    via_direct_link=True обходит только видимость.
    Открытость по ключам остаётся в силе.
    """
    nodes = doc.namespace.chain() if doc.namespace else []
    visible = via_direct_link or not (any(n.hidden for n in nodes) or doc.hidden)
    is_open = _all_satisfied(
        [n.access for n in nodes] + [doc.access], keys
    )
    return State(visible=visible, open=is_open)