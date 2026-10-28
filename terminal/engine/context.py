from dataclasses import dataclass

from machines.models import Session

DEFAULT_CWD = "/home"
# Ключ в Django-сессии: текущая папка открытого окна терминала. Хранится на сервере, браузер не может её подменить.
CWD_KEY = "terminal_cwd"


@dataclass
class TerminalContext:
    session: Session
    cwd: str = DEFAULT_CWD
    request: object = None      # запрос, если команде нужно состояние входа (мост); в тестах без него None

    @property
    def machine(self):
        return self.session.profile.machine

    @property
    def profile(self):
        return self.session.profile

    @property
    def user(self):
        return self.session.user

    @property
    def view(self):
        """Вид файловой системы машины для игрока: общий для команд одного запроса (после записи его сбрасывает invalidate)."""
        if getattr(self, "_view", None) is None:
            from filesystem.machine_view import MachineView

            self._view = MachineView(self.machine, self.user)
        return self._view

    def invalidate(self):
        if getattr(self, "_view", None) is not None:
            self._view.invalidate()

    def resolve_path(self, path: str) -> str:
        """Превращает путь (абсолютный или относительный) в нормальный
        абсолютный: сворачивает '.', '..' и лишние слэши.
        '..' в корне остаётся корнем, выйти выше / нельзя.
        """
        path = path.strip()

        if not path:
            return self.cwd

        if path.startswith("/"):
            parts = []
        else:
            parts = [p for p in self.cwd.split("/") if p]

        for part in path.split("/"):
            if part in ("", "."):
                continue

            if part == "..":
                if parts:
                    parts.pop()
                continue

            parts.append(part)

        return "/" + "/".join(parts)