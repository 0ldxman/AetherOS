from dataclasses import dataclass

from machines.models import Session

DEFAULT_CWD = "/home"


@dataclass
class TerminalContext:
    session: Session
    cwd: str = DEFAULT_CWD

    @property
    def machine(self):
        return self.session.profile.machine

    @property
    def profile(self):
        return self.session.profile

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