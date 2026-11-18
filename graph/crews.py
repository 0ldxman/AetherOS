"""Группы инициаторов (graph.models.Crew): вступление, выход, закрытие. Всё атомарно: «семеро одного не ждут» — кто успел, тот в группе."""
from django.db import transaction

from graph.models import Crew


def crew_of(graph, name):
    crew, _ = Crew.objects.get_or_create(graph=graph, name=str(name).strip())
    return crew


def join(graph, name, user, limit=0):
    """Добавить игрока. «joined» — он в группе (теперь или уже был); «full» — группа закрыта или набрала limit человек."""
    with transaction.atomic():
        crew, _ = Crew.objects.select_for_update().get_or_create(graph=graph, name=str(name).strip())
        if crew.members.filter(pk=user.pk).exists():
            return "joined"
        if crew.closed or (limit and crew.members.count() >= limit):
            return "full"
        crew.members.add(user)
        if limit and crew.members.count() >= limit:
            crew.closed = True                                   # набралось — вход закрывается сам
            crew.save(update_fields=["closed"])
    return "joined"


def leave(graph, name, user):
    crew_of(graph, name).members.remove(user)


def set_closed(graph, name, closed):
    Crew.objects.filter(pk=crew_of(graph, name).pk).update(closed=bool(closed))


def members(graph, name):
    """Логины игроков группы по порядку вступления (по номеру игрока)."""
    return [user.get_username() for user in crew_of(graph, name).members.order_by("pk")]
