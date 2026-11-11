"""Ящик учётки: письма это файлы на машине.

Ящик лежит в месте mail машины (по умолчанию /var/mail/<логин>): папки inbox, sent и trash. Письмо это файл формата msg
(mail.letters): заголовки и тело. Письма, положенные автором в ящик, видят все, кто входит под этой учёткой (улики
в чужих ящиках); доставленные игроку письма лежат в его слое (у других их нет). Прочитанность своя у каждого игрока
(MailMark), отложенные письма ждут в очереди (MailQueue) и приходят, когда игрок заглянет в почту.

Шифрованное письмо (файл со слоями) показывается заголовками, тело закрыто, пока игрок не снимет слои в терминале.
"""
import posixpath
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime

from django.utils import timezone

from mail import letters

FOLDERS = ("inbox", "sent", "trash")
DEFAULT_ROOT = "/var/mail/{login}"


@dataclass
class Row:
    path: str
    name: str
    folder: str
    letter: letters.Letter
    locked: bool
    read: bool
    arrived: object = None          # когда пришло (время машины игрока), для доставленных
    attachments: list = field(default_factory=list)

    @property
    def subject(self):
        return "(зашифровано)" if self.locked and not self.letter.subject else self.letter.subject or "(без темы)"


class Box:
    """Ящик учётки login на машине для читателя: игрока (user) или безымянного гостя (session_key)."""

    def __init__(self, machine, login, address, user=None, session_key="", profile=None):
        from filesystem.machine_view import view_for
        from machines.world import places

        self.machine, self.login, self.address = machine, login, address
        self.user, self.session_key, self.profile = user, session_key, profile
        self.view = view_for(machine, user, login=login)
        self.root = places.resolve(machine, "mail", login) or DEFAULT_ROOT.format(login=login)

    @classmethod
    def of_profile(cls, profile, user=None, session_key=""):
        return cls(profile.machine, profile.login, profile.mail, user=user, session_key=session_key, profile=profile)

    def folder(self, name):
        return f"{self.root}/{name}"

    def folder_of(self, path):
        rest = path[len(self.root) + 1:] if path.startswith(self.root + "/") else ""
        return rest.split("/", 1)[0] if rest else ""

    # --- чтение -------------------------------------------------------------------------------------------------

    def context(self):
        """Подстановки письма для этого игрока."""
        from machines.world.clock import now

        moment = now(self.machine, self.user)
        return {"login": self.login, "to": self.address, "address": self.address,
                "player": self.user.get_username() if self.user is not None else self.login, "date": f"{moment:%a, %d %b %Y %H:%M}"}

    def _marks(self):
        from mail.models import MailMark

        found = MailMark.objects.filter(machine=self.machine, path__startswith=self.root + "/")
        found = found.filter(user=self.user) if self.user is not None else found.filter(user=None, session_key=self.session_key)
        return {mark.path: mark for mark in found}

    def _row(self, entry, marks, context):
        from filesystem.content.window import layers_block

        locked = layers_block(entry)
        text = entry.body
        letter = letters.parse(letters.fill(text, context))
        if locked:
            letter = letters.Letter(letter.headers, "")
        mark = marks.get(entry.path)
        members = []
        if entry.item is not None and not locked:
            members = list(entry.item.members.select_related("item").order_by("path"))
        return Row(path=entry.path, name=posixpath.basename(entry.path), folder=self.folder_of(entry.path), letter=letter, locked=locked,
                   read=bool(mark and mark.read_at), arrived=mark.arrived_at if mark else None, attachments=members)

    def letters_in(self, folder):
        """Письма папки, новые сверху."""
        self.flush()
        path = self.folder(folder)
        if not self.view.is_directory(path):
            return []
        marks, context = self._marks(), self.context()
        rows = [self._row(entry, marks, context) for entry in self.view.children(path) if not entry.is_dir]
        rows.sort(key=_moment, reverse=True)
        return rows

    def letter(self, path):
        """Одно письмо ящика или None."""
        if not path.startswith(self.root + "/"):
            return None
        self.flush()
        entry = self.view.get(path)
        if entry is None or entry.is_dir:
            return None
        return self._row(entry, self._marks(), self.context())

    def attachment(self, path):
        """Вложение письма ящика по пути «письмо/имя» как запись файла (её открывают вьюверы) или None. Закрытое слоями письмо
        своих вложений не показывает."""
        from filesystem.content import archives

        letter_path, _, name = (path or "").rstrip("/").rpartition("/")
        row = self.letter(letter_path) if name else None
        if row is None or row.locked:
            return None
        entry = self.view.get(letter_path)
        return next((found for member, found in archives.members(self.view, entry) if member == name), None)

    def unread(self):
        return sum(1 for row in self.letters_in("inbox") if not row.read)

    def latest_unread(self):
        found = [row for row in self.letters_in("inbox") if not row.read]
        return found[0] if found else None

    # --- отметки ------------------------------------------------------------------------------------------------

    def mark(self, path, read=True):
        from mail.models import MailMark

        mark, _ = MailMark.objects.get_or_create(machine=self.machine, path=path, user=self.user,
                                                 session_key="" if self.user is not None else self.session_key)
        mark.read_at = timezone.now() if read else None
        mark.save(update_fields=["read_at"])

    # --- запись (только вошедший игрок: у гостя нет своего слоя) ------------------------------------------------

    def _free_name(self, folder, name):
        stem, ext = posixpath.splitext(name)
        ext = ext or ".msg"
        candidate, n = f"{stem}{ext}", 2
        while self.view.exists(f"{self.folder(folder)}/{candidate}"):
            candidate, n = f"{stem}-{n}{ext}", n + 1
        return f"{self.folder(folder)}/{candidate}"

    def _arrived(self, path):
        from mail.models import MailMark
        from machines.world.clock import now

        MailMark.objects.update_or_create(machine=self.machine, path=path, user=self.user, session_key="",
                                          defaults={"arrived_at": now(self.machine, self.user), "read_at": None})

    def deliver(self, item, folder="inbox", name=None):
        """Положить письмо автора (объект msg) в папку ящика в слое игрока. Возвращает путь."""
        path = self._free_name(folder, name or f"{item.slug or item.pk}.msg")
        self.view.put_item(path, item)
        self._arrived(path)
        return path

    def put_text(self, folder, name, text, read=False):
        """Своё письмо игрока (отправленное, возврат от MAILER-DAEMON) текстом в его слое."""
        path = self._free_name(folder, name)
        self.view.put_text(path, text)
        self._arrived(path)
        if read:
            self.mark(path, True)
        return path

    def trash(self, path):
        target = self._free_name("trash", posixpath.basename(path))
        self.view.move(path, target)
        self._carry(path, target)
        return target

    def restore(self, path, folder="inbox"):
        target = self._free_name(folder, posixpath.basename(path))
        self.view.move(path, target)
        self._carry(path, target)
        return target

    def _carry(self, old, new):
        from mail.models import MailMark

        MailMark.objects.filter(machine=self.machine, path=old, user=self.user).update(path=new)

    def queue(self, item, delay, folder="inbox"):
        """Письмо придёт через delay секунд (или сразу, если 0)."""
        from datetime import timedelta

        from mail.models import MailQueue

        if delay <= 0:
            return self.deliver(item, folder)
        MailQueue.objects.create(user=self.user, profile=self.profile, item=item, folder=folder,
                                 available_at=timezone.now() + timedelta(seconds=delay))
        return None

    def flush(self):
        """Доставить письма из очереди, срок которых подошёл."""
        from mail.models import MailQueue

        if self.user is None or self.profile is None:
            return 0
        due = list(MailQueue.objects.filter(user=self.user, profile=self.profile, available_at__lte=timezone.now()).select_related("item"))
        for waiting in due:
            self.deliver(waiting.item, waiting.folder)
            waiting.delete()
        return len(due)


def _moment(row):
    if row.arrived is not None:
        return row.arrived.timestamp()
    try:
        return parsedate_to_datetime(row.letter.get("Date")).timestamp()
    except (TypeError, ValueError, IndexError):
        return 0.0


def box_for(request):
    """Ящик того, кто сейчас за рабочим столом: учётка сессии игрока или гость witness на своей машине. None: негде."""
    from machines.current import active_session, current_machine
    from users.aether_auth import GUEST_LOGIN

    machine = current_machine(request)
    if machine is None:
        return None
    if request.user.is_authenticated:
        profile = active_session(request).profile
        return Box.of_profile(profile, user=request.user)
    session = request.session
    if getattr(session, "session_key", None) is None and hasattr(session, "save"):
        session.save()
    return Box(machine, GUEST_LOGIN, f"{GUEST_LOGIN}@{machine.label}", session_key=getattr(session, "session_key", "") or "")


def summary(box):
    """Для приветствия узла: сколько непрочитанных во входящих и от кого последнее."""
    from machines.world.dates import ago

    latest = box.latest_unread()
    return {
        "unread": box.unread(),
        "sender": latest.letter.sender if latest else "",
        "ago": ago(latest.arrived) if latest and latest.arrived else "",
    }
