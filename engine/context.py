"""Контекст действия: кто и где сейчас действует. Механика собирает его из того, что у неё под рукой, и отдаёт движку."""
from dataclasses import dataclass, field

WORLD, USER, ACCOUNT, SESSION = "world", "user", "account", "session"


@dataclass
class Ctx:
    source: str = ""                 # откуда действие: «письмо guard / шаг ask», «триггер act-2», «ответчик BOREAS»
    user: object = None              # игрок
    box: object = None               # mail.boxes.Box: учётка игрока на машине (ключи, файлы, письма)
    session: bool = False            # есть живой браузер, которому вернутся эффекты (alert, open)
    depth: int = 0                   # глубина цепочки мира (триггер → действие → триггер)
    effects: list = field(default_factory=list)
    host: dict = field(default_factory=dict)      # локальные действия хозяина: {"goto": функция(action, ctx)}

    @property
    def profile(self):
        return getattr(self.box, "profile", None)

    def provides(self):
        """Что доступно в этом контексте: world всегда; user, если есть игрок; account, если есть его учётка; session — живой браузер."""
        found = {WORLD}
        if self.user is not None:
            found.add(USER)
        if self.box is not None and self.user is not None:
            found.add(ACCOUNT)
        if self.session and self.box is not None:
            found.add(SESSION)
        return found
