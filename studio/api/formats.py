"""Форматы файлов и кодировки: таблицы автора. Логика в filesystem.manager.formats."""
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from filesystem.manager import formats as logic
from filesystem.models import FileEncoding, FileFormat

router = Router(tags=["file-formats"])


class FmtPart(Schema):
    name: str
    source: str
    value: str = ""


class FmtRow(Schema):
    name: str
    title: str
    extension: str
    aliases: str
    kind: str
    content: str
    markup: bool
    editable: bool
    used: int                    # объектов с этим форматом
    part_count: int


class FmtDetail(Schema):
    name: str
    title: str
    extension: str
    aliases: str
    kind: str
    magic: str
    template: str
    content: str
    markup: bool
    editable: bool
    used: int
    part_list: list[FmtPart]


class FmtIn(Schema):
    name: str
    title: str = ""
    extension: str = ""
    aliases: str = ""
    kind: str = "signature"
    magic: str = ""
    template: str = ""
    content: str = "text_asset"
    markup: bool = False
    editable: bool = False
    part_list: list[FmtPart] = []


class EncRow(Schema):
    name: str
    title: str
    kind: str
    param: str


class EncIn(Schema):
    name: str
    title: str = ""
    kind: str
    param: str = ""


class FmtDone(Schema):
    ok: bool = True


def _raise(error):
    raise ValidationError(error.errors)


def _detail(item, count=None):
    return FmtDetail(
        name=item.name, title=item.title, extension=item.extension, aliases=item.aliases, kind=item.kind, magic=item.magic, template=item.template,
        content=item.content, markup=item.markup, editable=item.editable, used=logic.used(item.name) if count is None else count,
        part_list=[FmtPart(name=p.name, source=p.source, value=p.value) for p in item.parts.all()],
    )


@router.get("/file-formats", response=list[FmtRow])
def rows(request):
    counts = logic.counts()
    return [
        FmtRow(name=f.name, title=f.title, extension=f.extension, aliases=f.aliases, kind=f.kind, content=f.content, markup=f.markup, editable=f.editable,
               used=counts.get(f.name, 0), part_count=f.parts.count())
        for f in FileFormat.objects.prefetch_related("parts").order_by("name")
    ]


@router.get("/file-formats/{name}", response=FmtDetail)
def detail(request, name: str):
    return _detail(get_object_or_404(FileFormat, name=name))


@router.post("/file-formats", response=FmtDetail)
def create(request, body: FmtIn):
    try:
        saved = logic.save_format(None, body.dict(), [p.dict() for p in body.part_list])
    except logic.FormatError as error:
        _raise(error)
    return _detail(saved)


@router.put("/file-formats/{name}", response=FmtDetail)
def update(request, name: str, body: FmtIn):
    try:
        saved = logic.save_format(get_object_or_404(FileFormat, name=name), body.dict(), [p.dict() for p in body.part_list])
    except logic.FormatError as error:
        _raise(error)
    return _detail(saved)


@router.delete("/file-formats/{name}", response=FmtDone)
def remove(request, name: str):
    try:
        logic.delete_format(get_object_or_404(FileFormat, name=name))
    except logic.FormatError as error:
        _raise(error)
    return FmtDone()


@router.get("/file-encodings", response=list[EncRow])
def encodings(request):
    return [EncRow(name=e.name, title=e.title, kind=e.kind, param=e.param) for e in FileEncoding.objects.order_by("name")]


@router.post("/file-encodings", response=EncRow)
def create_encoding(request, body: EncIn):
    try:
        e = logic.save_encoding(None, body.dict())
    except logic.FormatError as error:
        _raise(error)
    return EncRow(name=e.name, title=e.title, kind=e.kind, param=e.param)


@router.put("/file-encodings/{name}", response=EncRow)
def update_encoding(request, name: str, body: EncIn):
    """Имя кодировки не меняется: игроки называют её в командах и слоях."""
    found = get_object_or_404(FileEncoding, name=name)
    try:
        e = logic.save_encoding(found, {**body.dict(), "name": found.name})
    except logic.FormatError as error:
        _raise(error)
    return EncRow(name=e.name, title=e.title, kind=e.kind, param=e.param)


@router.delete("/file-encodings/{name}", response=FmtDone)
def remove_encoding(request, name: str):
    logic.delete_encoding(get_object_or_404(FileEncoding, name=name))
    return FmtDone()
