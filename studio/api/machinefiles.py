"""Файлы машины: её файловая система целиком (все диски вместе), и правки, которые ложатся в диск отличий машины.

Логика в filesystem.manager.overlay; здесь схемы и коды ответов. Общие диски не меняются: правка общего файла создаёт его копию в
диске отличий, скрытие кладёт надгробие, «сбросить» убирает копию и возвращает то, что лежит ниже.
"""
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from filesystem.manager import overlay
from machines.models import Machine

router = Router(tags=["machine-files"])


class MachineFileItem(Schema):
    id: int
    slug: str
    name: str
    format: str
    used: int
    size: int | None


class MachineFileRow(Schema):
    path: str
    name: str
    kind: str                    # dir | file | deleted
    volume: str                  # слаг диска, из которого пришёл
    mark: str                    # base | override | added | deleted | remote | ""
    private: bool                # диск правится на месте (смонтирован только на эту машину)
    hidden: bool
    system: bool
    item: MachineFileItem | None
    owner: str = ""
    group: str = ""
    mode: str = ""


class MachineFiles(Schema):
    rows: list[MachineFileRow]
    overlay: int | None          # диск отличий машины
    changed: int                 # сколько путей изменено на этой машине (перекрыто, добавлено, скрыто)


class MachineFilePath(Schema):
    path: str


class MachineFileNew(Schema):
    parent: str = "/"
    name: str


class MachineFileRename(Schema):
    path: str
    name: str


class MachineFileMove(Schema):
    path: str
    dest: str
    name: str | None = None


class MachineFileRights(Schema):
    path: str
    owner: str = ""
    group: str = ""
    mode: str = ""


class MachineFileOpen(Schema):
    kind: str                    # item | text
    item: int | None = None
    volume: int | None = None
    placement: int | None = None


class MachineFileDone(Schema):
    ok: bool = True


def _machine(machine_id):
    return get_object_or_404(Machine.objects.select_related("overlay"), pk=machine_id)


@router.get("/{int:machine_id}/files", response=MachineFiles)
def files(request, machine_id: int):
    machine = _machine(machine_id)
    rows = overlay.machine_data(machine)["rows"]
    return MachineFiles(
        rows=[MachineFileRow(**{**row, "item": row["item"]}) for row in rows],
        overlay=machine.overlay_id,
        changed=sum(1 for row in rows if row["mark"] in ("override", "added", "deleted")),
    )


@router.post("/{int:machine_id}/files/open", response=MachineFileOpen)
def open_file(request, machine_id: int, body: MachineFilePath):
    return MachineFileOpen(**overlay.open_for_edit(_machine(machine_id), body.path))


@router.post("/{int:machine_id}/files/folder", response=MachineFileDone)
def new_folder(request, machine_id: int, body: MachineFileNew):
    overlay.new_folder(_machine(machine_id), body.parent, body.name)
    return MachineFileDone()


@router.post("/{int:machine_id}/files/file", response=MachineFileOpen)
def new_file(request, machine_id: int, body: MachineFileNew):
    """Новый файл без объекта, любое имя и расширение."""
    placement = overlay.new_text_file(_machine(machine_id), body.parent, body.name)
    return MachineFileOpen(kind="text", volume=placement.volume_id, placement=placement.pk)


@router.post("/{int:machine_id}/files/rename", response=MachineFileDone)
def rename(request, machine_id: int, body: MachineFileRename):
    overlay.rename(_machine(machine_id), body.path, body.name)
    return MachineFileDone()


@router.post("/{int:machine_id}/files/move", response=MachineFileDone)
def move(request, machine_id: int, body: MachineFileMove):
    overlay.move(_machine(machine_id), body.path, body.dest, body.name)
    return MachineFileDone()


@router.post("/{int:machine_id}/files/copy", response=MachineFileDone)
def copy(request, machine_id: int, body: MachineFileMove):
    overlay.copy(_machine(machine_id), body.path, body.dest, body.name)
    return MachineFileDone()


@router.post("/{int:machine_id}/files/delete", response=MachineFileDone)
def delete(request, machine_id: int, body: MachineFilePath):
    """Убрать из вида машины: свой файл удаляется, файл общего диска скрывается."""
    overlay.delete(_machine(machine_id), body.path)
    return MachineFileDone()


@router.post("/{int:machine_id}/files/restore", response=MachineFileDone)
def restore(request, machine_id: int, body: MachineFilePath):
    overlay.restore(_machine(machine_id), body.path)
    return MachineFileDone()


@router.post("/{int:machine_id}/files/reset", response=MachineFileDone)
def reset(request, machine_id: int, body: MachineFilePath):
    """Сбросить правку: убрать копию из диска отличий, вернётся файл общего диска."""
    overlay.reset(_machine(machine_id), body.path)
    return MachineFileDone()


@router.post("/{int:machine_id}/files/rights", response=MachineFileDone)
def rights(request, machine_id: int, body: MachineFileRights):
    overlay.set_rights(_machine(machine_id), body.path, body.owner, body.group, body.mode)
    return MachineFileDone()
