"""Вырезки (blk): новый файл игрока, который читается как окно в байтах другого файла."""
import uuid

from filesystem.models import FileSlice, MachineFile, SessionFile

STORE = "/.slices"


def make(session, source, state, start, end, path):
    """Положить в сессию файл path, который читается как source[start:end] с прогрессом state. Возвращает SessionFile."""
    holder = MachineFile.objects.create(
        machine=session.profile.machine, path=f"{STORE}/{uuid.uuid4().hex}", url="slice", delivered_only=True,
    )
    FileSlice.objects.create(file=holder, source=source, state=state or "", start=start, end=end)
    return SessionFile.objects.create(session=session, file=holder, path=path)
