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
    rows = SessionFile.objects.filter(
        session=session, deleted_at__isnull=True, path__startswith=SECRETS + "/", file__url__startswith=PREFIX,
    ).values_list("file__url", flat=True)
    return frozenset(url[len(PREFIX):] for url in rows)


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
