"""Кто вошёл и справочники, которые нужны всем экранам."""
from ninja import Router, Schema

from secure.keys import key_rows

router = Router(tags=["catalog"])


class MeRights(Schema):
    sections: dict[str, str]     # раздел -> none|read|edit
    actions: list[str]           # опасные действия, которые разрешены
    team: str                    # read|edit: управлять командой может только суперадмин


class Me(Schema):
    username: str
    superuser: bool
    rights: MeRights


class Format(Schema):
    name: str
    title: str
    extension: str
    markup: bool
    content: str
    editable: bool


class AppIcon(Schema):
    name: str
    title: str
    ascii: str                   # текстовый значок: его рисует стиль tui


class AppIconStyle(Schema):
    slug: str
    label: str
    urls: dict[str, str]         # имя иконки -> адрес картинки в наборе этого стиля (пусто у стилей без картинок)


class AppIcons(Schema):
    icons: list[AppIcon]
    styles: list[AppIconStyle]


class Key(Schema):
    slug: str
    description: str


@router.get("/me", response=Me)
def me(request):
    from team.rights import summary

    return Me(username=request.user.get_username(), superuser=request.user.is_superuser, rights=MeRights(**summary(request.user)))


@router.get("/app-icons", response=AppIcons)
def app_icons(request):
    """Каталог иконок приложений рабочего стола и их картинки по стилям ОС."""
    from desktop import icons
    from machines.world.styles import STYLES

    return AppIcons(
        icons=[AppIcon(name=name, title=title, ascii=text) for name, title, text in icons.CATALOG],
        styles=[AppIconStyle(slug=slug, label=style.label, urls={name: icons.icon_url(slug, name) for name in icons.NAMES}) for slug, style in STYLES.items()],
    )


@router.get("/formats", response=list[Format])
def formats(request):
    from filesystem.models import FileFormat

    return [
        Format(name=f.name, title=f.title, extension=f.extension, markup=f.markup, content=f.content, editable=f.editable)
        for f in FileFormat.objects.order_by("name")
    ]


class Template(Schema):
    id: int
    name: str
    folders: list[str]


@router.get("/templates", response=list[Template])
def templates(request):
    """Шаблоны файловой структуры для корня новой машины."""
    from filesystem.models import VolumeTemplate

    return [Template(id=t.pk, name=t.name, folders=t.paths()) for t in VolumeTemplate.objects.order_by("name")]


@router.get("/keys", response=list[Key])
def keys(request):
    return [Key(**row) for row in key_rows()]
