"""Кто вошёл и справочники, которые нужны всем экранам."""
from ninja import Router, Schema

from secure.keys import key_rows

router = Router(tags=["catalog"])


class Me(Schema):
    username: str
    superuser: bool


class Format(Schema):
    name: str
    title: str
    extension: str
    markup: bool
    content: str
    editable: bool


class Key(Schema):
    slug: str
    description: str


@router.get("/me", response=Me)
def me(request):
    return Me(username=request.user.get_username(), superuser=request.user.is_superuser)


@router.get("/formats", response=list[Format])
def formats(request):
    from filesystem.models import FileFormat

    return [
        Format(name=f.name, title=f.title, extension=f.extension, markup=f.markup, content=f.content, editable=f.editable)
        for f in FileFormat.objects.order_by("name")
    ]


@router.get("/keys", response=list[Key])
def keys(request):
    return [Key(**row) for row in key_rows()]
