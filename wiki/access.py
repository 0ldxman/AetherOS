from dataclasses import dataclass
from secure.access import satisfied


@dataclass(frozen=True)
class State:
    """Итог проверки: видна ли запись и открыта ли она."""
    visible: bool
    open: bool


def guest_keys():
    """Заглушка: у гостя нет ключей.

    Настоящие ключи появятся вместе с машинами и сессиями.
    """
    return frozenset()


def _all_satisfied(conditions, keys):
    # пустое условие satisfied считает открытым, отдельно его обрабатывать не нужно
    return all(satisfied(c, keys) for c in conditions)


def namespace_state(namespace, keys):
    """Состояние неймспейса: условия всей цепочки от корня до него."""
    nodes = namespace.chain()
    return State(
        visible=_all_satisfied([n.visibility for n in nodes], keys),
        open=_all_satisfied([n.access for n in nodes], keys),
    )


def document_state(doc, keys, via_direct_link=False):
    """Состояние записи: условия неймспейсов цепочки плюс условия самой записи.

    via_direct_link=True обходит только видимость.
    Открытость по ключам остаётся в силе.
    """
    nodes = doc.namespace.chain() if doc.namespace else []
    visible = via_direct_link or _all_satisfied(
        [n.visibility for n in nodes] + [doc.visibility], keys
    )
    is_open = _all_satisfied(
        [n.access for n in nodes] + [doc.access], keys
    )
    return State(visible=visible, open=is_open)