"""Ключи игрока: файлы в его скрытой папке /home/.secrets.

Ключ, извлечённый из байтов файла (kex), появляется в сессии игрока файлом /home/.secrets/<слаг>. Ключи игрока на сессии
это слаги этих файлов: удалил файл, потерял ключ. Содержимое файла берётся по адресу keys/<слаг> (блок ключа), а сам файл
машины скрыт ото всех (delivered_only) и виден только там, куда его положили.
"""
from filesystem.models import MachineFile, SessionFile

SECRETS = "/home/.secrets"
STORE = "/.keystore"
PREFIX = "keys/"


def path_of(slug):
    return f"{SECRETS}/{slug}"


def slugs_of(session):
    """Слаги ключей, лежащих в папке секретов этой сессии."""
    if session is None:
        return frozenset()
    return frozenset(slug for _, slug in held(session))


def held(session):
    """Ключи в папке секретов: список (имя файла, слаг). Имя файла и ключ это разное: ключ задаёт содержимое (адрес keys/<слаг>).

    Это и файлы, которые игрок получил (запись сессии), и файлы, лежащие там на самой машине (админ), пока игрок их не
    удалил и не переместил."""
    if session is None:
        return []
    prefix = SECRETS + "/"
    rows = list(SessionFile.objects.filter(session=session).select_related("file"))
    touched = {row.file_id for row in rows}
    found = {}
    for file in MachineFile.objects.filter(machine=session.profile.machine, path__startswith=prefix, url__startswith=PREFIX):
        if file.id not in touched and not file.delivered_only:                    # как её видит файловая система
            found[file.path] = file.url
    for row in rows:
        if row.deleted_at is None and row.path.startswith(prefix) and row.file.url.startswith(PREFIX):
            found[row.path] = row.file.url
    return [
        (path[len(prefix):], url[len(PREFIX):]) for path, url in sorted(found.items()) if "/" not in path[len(prefix):]
    ]


def put(session, slug):
    """Положить ключ в папку секретов сессии. Возвращает (путь, создан ли заново)."""
    machine_file, _ = MachineFile.objects.get_or_create(
        machine=session.profile.machine,
        path=f"{STORE}/{slug}",
        defaults={"url": PREFIX + slug, "delivered_only": True},
    )
    row, created = SessionFile.objects.get_or_create(
        session=session, path=path_of(slug), defaults={"file": machine_file},
    )
    if not created and row.deleted_at is not None:
        row.deleted_at = None
        row.file = machine_file
        row.save(update_fields=["deleted_at", "file"])
        created = True
    return row.path, created


STORE_SIG = "/.sigstore"


def put_signature(session, slug, hexhash, path):
    """Файл подписи ключа slug под хешем hexhash в сессии игрока по пути path. Возвращает SessionFile."""
    holder, _ = MachineFile.objects.get_or_create(
        machine=session.profile.machine,
        path=f"{STORE_SIG}/{slug}-{hexhash[:16]}",
        defaults={"url": f"sig/{slug}/{hexhash}", "delivered_only": True},
    )
    row = SessionFile.objects.filter(session=session, path=path).first()
    if row is None:
        return SessionFile.objects.create(session=session, file=holder, path=path)
    row.file, row.deleted_at, row.state = holder, None, ""
    row.save(update_fields=["file", "deleted_at", "state"])
    return row
