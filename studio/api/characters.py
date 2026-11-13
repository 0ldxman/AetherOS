"""Персонажи в Студии: карточка (кто, как говорит, что знает), код и цвет, кто ведёт, каналы (адреса почты и позывные эфира). Логика в characters/logic.py."""
import re

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from air.models import Station
from characters import logic
from characters.models import Character
from mail.models import Persona

router = Router(tags=["characters"])

_CODE = re.compile(r"^[A-Z0-9]{3}$")
_CALLSIGN = re.compile(r"^[A-Z][A-Z0-9-]{1,15}$")


class ChErrors(Schema):
    fields: dict[str, str]


class ChRow(Schema):
    id: int
    code: str
    name: str
    callsign: str
    color: int
    status: str
    owner: str
    mail: list[str]
    air: list[str]


class ChOut(ChRow):
    about: str
    voice: str
    knows: str
    note: str
    owner_id: int | None
    personas: list[int]
    stations: list[int]


class ChIn(Schema):
    name: str
    code: str = ""
    callsign: str = ""
    color: int = 0
    status: str = "active"
    about: str = ""
    voice: str = ""
    knows: str = ""
    note: str = ""
    owner_id: int | None = None
    personas: list[int] = []
    stations: list[int] = []


class ChChannel(Schema):
    id: int
    label: str
    character: int | None


class ChAuthor(Schema):
    id: int
    username: str


class ChOptions(Schema):
    personas: list[ChChannel]
    stations: list[ChChannel]
    authors: list[ChAuthor]


def _row(found):
    found_channels = logic.channels(found)
    return dict(id=found.pk, code=found.code, name=found.name, callsign=found.callsign, color=found.color, status=found.status,
                owner=found.owner.get_username() if found.owner_id else "", mail=found_channels["mail"], air=found_channels["air"])


def _out(found):
    return ChOut(**_row(found), about=found.about, voice=found.voice, knows=found.knows, note=found.note, owner_id=found.owner_id,
                 personas=list(found.personas.values_list("pk", flat=True)), stations=list(found.stations.values_list("pk", flat=True)))


@transaction.atomic
def _apply(found, body):
    errors = {}
    name = body.name.strip()
    if not name:
        errors["name"] = "Нужно имя."
    code = body.code.strip().upper() or logic.code_for(name)
    if not _CODE.match(code):
        errors["code"] = "Код: три знака, латинские буквы и цифры."
    elif Character.objects.filter(code=code).exclude(pk=found.pk).exists():
        errors["code"] = "Такой код уже у другого персонажа."
    callsign = body.callsign.strip().upper()
    if callsign and not _CALLSIGN.match(callsign):
        errors["callsign"] = "Позывной: 2–16 знаков, латиница, цифры и дефис, с буквы."
    elif callsign and Character.objects.filter(callsign=callsign).exclude(pk=found.pk).exists():
        errors["callsign"] = "Такой позывной уже у другого персонажа."
    if body.status not in Character.Status.values:
        errors["status"] = "Неизвестный статус."
    owner = None
    if body.owner_id is not None:
        owner = get_user_model().objects.filter(pk=body.owner_id, is_staff=True).first()
        if owner is None:
            errors["owner_id"] = "Вести персонажа может только автор."
    if errors:
        return errors
    found.name, found.code, found.callsign, found.color = name[:120], code, callsign, body.color % logic.COLORS
    found.status, found.about, found.voice, found.knows, found.note, found.owner = body.status, body.about, body.voice, body.knows, body.note, owner
    found.save()
    # каналы: отмеченные переходят к этому персонажу, снятые отвязываются
    Persona.objects.filter(character=found).exclude(pk__in=body.personas).update(character=None)
    Persona.objects.filter(pk__in=body.personas).update(character=found)
    Station.objects.filter(character=found).exclude(pk__in=body.stations).update(character=None)
    Station.objects.filter(pk__in=body.stations).update(character=found)
    return {}


@router.get("", response=list[ChRow])
def index(request):
    return [ChRow(**_row(found)) for found in Character.objects.select_related("owner").prefetch_related("personas", "stations")]


@router.get("/options", response=ChOptions)
def options(request):
    return ChOptions(
        personas=[ChChannel(id=p.pk, label=p.address, character=p.character_id) for p in Persona.objects.order_by("address")],
        stations=[ChChannel(id=s.pk, label=s.name, character=s.character_id) for s in Station.objects.order_by("name")],
        authors=[ChAuthor(id=u.pk, username=u.get_username()) for u in get_user_model().objects.filter(is_staff=True).order_by("username")],
    )


@router.post("", response={200: ChOut, 400: ChErrors})
def create(request, body: ChIn):
    found = Character(color=logic.color_for(body.callsign or body.name))
    errors = _apply(found, body)
    if errors:
        return 400, {"fields": errors}
    return _out(found)


@router.get("/{character_id}", response=ChOut)
def detail(request, character_id: int):
    return _out(get_object_or_404(Character, pk=character_id))


@router.put("/{character_id}", response={200: ChOut, 400: ChErrors})
def update(request, character_id: int, body: ChIn):
    found = get_object_or_404(Character, pk=character_id)
    errors = _apply(found, body)
    if errors:
        return 400, {"fields": errors}
    return _out(found)


@router.delete("/{character_id}", response={204: None})
def delete(request, character_id: int):
    get_object_or_404(Character, pk=character_id).delete()
    return 204, None
