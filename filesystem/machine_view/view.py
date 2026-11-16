"""Вид файловой системы машины для игрока (docs/storage-spec.md, раздел 3)."""
from filesystem.machine_view.build import BuildMixin
from filesystem.machine_view.reading import ReadMixin
from filesystem.machine_view.remote import RemoteMixin
from filesystem.machine_view.writes import WriteMixin


def world_of(user):
    """Экземпляр, который видит игрок: None — мир, песочный игрок — его песочница."""
    return user if getattr(user, "sandbox_of_id", None) else None


class MachineView(BuildMixin, ReadMixin, RemoteMixin, WriteMixin):
    """Вид машины для игрока: база и изменения его экземпляра — мира или песочницы автора (user=None: только база, вид автора)."""

    generation = 0                          # растёт при каждой записи через любой вид: собранное раньше устарело

    def __init__(self, machine, user=None, principal=None, trail=frozenset(), _state=None, login=None, live=False):
        self.machine = machine
        self.user = user
        self.world = world_of(user)         # чьи изменения поверх базы
        self.live = live or user is not None    # видны изменения мира; user=None без live — только база (вид автора)
        # логин учётки для шаблонных папок {login}: явный, иначе учётка подключения, иначе последняя сессия игрока на машине.
        # Без игрока и без логина (вид автора) шаблонная папка видна как есть.
        self.login = login or getattr(principal, "login", None) or (session_login(machine, user) if user is not None else None)
        self.principal = principal          # кто действует (filesystem/rights.py); None: система, права не проверяются
        self.trail = trail                  # машины, через которые пришло подключение (чтобы цепочка не замкнулась)
        self._state = _state if _state is not None else {}          # собранное: общее у копий вида с разными правами

    def fork(self, principal):
        """Тот же вид (собранное общее) с другими правами."""
        return MachineView(self.machine, self.user, principal, self.trail, self._state, login=self.login, live=self.live)

    def _cache(self):
        """Собранное состояние, если оно не старше последней записи, иначе пустое."""
        if self._state.get("generation") != MachineView.generation:
            self._state.clear()
            self._state["generation"] = MachineView.generation
        return self._state


def session_login(machine, user):
    """Логин учётки игрока на машине: последняя сессия, иначе привязанная к нему учётка, иначе None."""
    from machines.models import MachineProfile, Session

    found = Session.objects.filter(user=user, profile__machine=machine).order_by("-seen_at", "-pk").values_list("profile__login", flat=True).first()
    return found or MachineProfile.objects.filter(machine=machine, user=user).values_list("login", flat=True).first()


def view_for(machine, user=None, principal=None, login=None, live=False):
    """Вид машины для игрока: за запрос собирается один раз, а права (principal) накладываются копией, собранное у копий общее.
    live: без игрока — мир, как его видят все (система: ящики, письма персонажей), а не только база."""
    from machines import memo

    login = login or getattr(principal, "login", None) or (session_login(machine, user) if user is not None else None)
    live = live or user is not None
    base = memo.cached(("view", machine.pk, user.pk if user is not None else None, login, live),
                       lambda: MachineView(machine, user, login=login, live=live))      # mnt и логин — у игрока
    return base if principal is None else base.fork(principal)
