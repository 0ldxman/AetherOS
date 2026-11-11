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
    def principal(self):
        """Кто действует: запись, её группы и привилегии."""
        if getattr(self, "_principal", None) is None:
            from machines.access.groups import principal_for

            self._principal = principal_for(self.profile)
        return self._principal

    def require(self, path, action):
        """Права на путь или Denied (Permission denied)."""
        from filesystem import rights

        rights.check(self.view, self.principal, path, action)

    def need(self, privilege):
        """Привилегия записи или NotPermitted (Operation not permitted)."""
        from filesystem import rights

        if not self.principal.has(privilege):
            raise rights.NotPermitted(privilege)

    @property
    def home(self):
        from terminal.engine.home import home_of

        if getattr(self, "_home", None) is None:
            self._home = home_of(self.session)
        return self._home

    @property
    def trash_dir(self):
        """Корзина записи: место trash машины (по умолчанию {home}/.trash)."""
        from machines.world import places

        return places.resolve(self.machine, "trash", self.profile.login) or "/trash"

    @property
    def user(self):
        return self.session.user

    @property
    def view(self):
        """Вид файловой системы машины для игрока: общий для команд одного запроса (после записи его сбрасывает invalidate)."""
        if getattr(self, "_view", None) is None:
            from filesystem.machine_view import view_for

            self._view = view_for(self.machine, self.user, self.principal)
        return self._view

    def invalidate(self):
        if getattr(self, "_view", None) is not None:
            self._view.invalidate()

    @property
    def style(self):
        """Диалект путей машины (machines.world.dialect): как игрок пишет пути и как терминал их показывает. Читается раз на команду."""
        if getattr(self, "_style", None) is None:
            self._style = self.machine.path_style
        return self._style

    def resolve_path(self, path: str) -> str:
        """Путь, как его ввёл игрок в диалекте машины (абсолютный или относительный к cwd), -> канонический абсолютный.
        '..' в корне (и выше диска) остаётся там же. В диалектах без регистра имя сверяется с файлами без учёта регистра.
        Неразборчивый путь: PathSyntax (исполнитель печатает её как ошибку команды)."""
        from machines.world.dialect import CASELESS, parse

        found = parse(path, self.style, self.cwd)
        return self._real_case(found) if self.style in CASELESS else found

    def _real_case(self, path):
        """Каждая часть пути в написании настоящего файла, если такой есть (иначе как ввели: для новых файлов)."""
        parts, here = [], "/"
        for part in (p for p in path.split("/") if p):
            names = {entry.name.casefold(): entry.name for entry in self.view.children(here)}
            parts.append(part if part in names.values() else names.get(part.casefold(), part))
            here = "/" + "/".join(parts)
        return "/" + "/".join(parts)

    def show(self, path, is_dir=True):
        """Канонический путь в диалекте машины (для вывода игроку)."""
        from machines.world.dialect import to_display

        return to_display(path, self.style, is_dir)
