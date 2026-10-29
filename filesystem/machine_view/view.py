"""Вид файловой системы машины для игрока (docs/storage-spec.md, раздел 3)."""
from filesystem.machine_view.build import BuildMixin
from filesystem.machine_view.reading import ReadMixin
from filesystem.machine_view.remote import RemoteMixin
from filesystem.machine_view.writes import WriteMixin


class MachineView(BuildMixin, ReadMixin, RemoteMixin, WriteMixin):
    """Вид машины для игрока (user=None: только база, без слоя игрока)."""

    generation = 0                          # растёт при каждой записи через любой вид: собранное раньше устарело

    def __init__(self, machine, user=None, principal=None, trail=frozenset(), _state=None):
        self.machine = machine
        self.user = user
        self.principal = principal          # кто действует (filesystem/rights.py); None: система, права не проверяются
        self.trail = trail                  # машины, через которые пришло подключение (чтобы цепочка не замкнулась)
        self._state = _state if _state is not None else {}          # собранное: общее у копий вида с разными правами

    def fork(self, principal):
        """Тот же вид (собранное общее) с другими правами."""
        return MachineView(self.machine, self.user, principal, self.trail, self._state)

    def _cache(self):
        """Собранное состояние, если оно не старше последней записи, иначе пустое."""
        if self._state.get("generation") != MachineView.generation:
            self._state.clear()
            self._state["generation"] = MachineView.generation
        return self._state


def view_for(machine, user=None, principal=None):
    """Вид машины для игрока: за запрос собирается один раз, а права (principal) накладываются копией, собранное у копий общее."""
    from machines import memo

    base = memo.cached(("view", machine.pk, user.pk if user is not None else None), lambda: MachineView(machine, user))
    return base if principal is None else base.fork(principal)
