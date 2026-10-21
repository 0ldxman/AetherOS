from dataclasses import dataclass
from pathlib import PurePosixPath

from machines.models import Session


@dataclass
class TerminalContext:
    session: Session
    cwd: str = "/home"

    @property
    def machine(self):
        return self.session.profile.machine

    @property
    def profile(self):
        return self.session.profile

    def resolve_path(self, path: str) -> str:
        path = path.strip()

        if not path:
            path = self.cwd

        if path.startswith("/"):
            resolved = PurePosixPath(path)
        else:
            resolved = PurePosixPath(self.cwd) / path

        normalized = str(resolved)

        if not normalized.startswith("/"):
            normalized = f"/{normalized}"

        return normalized