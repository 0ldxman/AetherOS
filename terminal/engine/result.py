from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    output: str = ""
    exit_code: int = 0

    @property
    def success(self) -> bool:
        return self.exit_code == 0