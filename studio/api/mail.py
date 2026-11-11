"""Почта: персонажи и сценарии переписки. Логика в mail.authoring (документ сценария, проверка, песочница)."""
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from mail import authoring
from mail.models import Conversation, Persona, Variant

router = Router(tags=["mail"])


class MlTalkRow(Schema):
    id: int
    slug: str
    title: str
    steps: int
    persona: int


class MlPersona(Schema):
    id: int
    address: str
    name: str
    signature: str
    note: str
    conversations: list[MlTalkRow]


class MlPersonaIn(Schema):
    address: str
    name: str = ""
    signature: str = ""
    note: str = ""


class MlNewTalk(Schema):
    persona: int
    title: str
    slug: str


class MlLetter(Schema):
    item: str | None = None
    subject: str = ""
    text: str = ""


class MlAttachment(Schema):
    kind: str = ""                 # "" | item | key | signed
    slug: str = ""


class MlVariant(Schema):
    id: int | None = None
    title: str = ""
    mode: str = "reply"
    text: str = ""
    forward_of: str | None = None
    condition: str = ""
    need_flags: list[str] = []
    deny_flags: list[str] = []
    account: int | None = None
    closed: str = "mystery"
    attachment: MlAttachment = MlAttachment()
    max_attempts: int = 0
    outcomes: dict[str, list[dict[str, Any]]] = {}


class MlStep(Schema):
    id: int | None = None
    name: str
    x: float = 0
    y: float = 0
    opening: bool = False
    letter: MlLetter = MlLetter()
    letter_delay: int = 0
    variants: list[MlVariant] = []


class MlDoc(Schema):
    title: str
    slug: str
    note: str = ""
    persona: int
    steps: list[MlStep] = []


class MlProblem(Schema):
    level: str
    step: str | None
    variant: int | None
    text: str


class MlTalk(Schema):
    id: int
    doc: MlDoc
    problems: list[MlProblem]


class MlPick(Schema):
    slug: str
    label: str
    format: str
    subject: str = ""              # у писем: тема и текст, чтобы выбранное письмо сразу открылось в редакторе
    text: str = ""


class MlAccount(Schema):
    id: int
    label: str


class MlPicks(Schema):
    items: list[MlPick]
    accounts: list[MlAccount]
    flags: list[str]


class MlTry(Schema):
    variants: list[MlVariant]
    keys: list[str] = []
    flags: list[str] = []
    account: int | None = None
    pick: int | None = None
    typed: str = ""
    used: int = 0
    attachment: str | None = None


class MlOffer(Schema):
    index: int
    title: str
    shown: str                    # open | mystery | hidden
    layout: list[dict[str, Any]]


class MlResult(Schema):
    kind: str                     # ok | wrong | exhausted | mismatch | closed
    verdict: str
    words: list[str]
    sockets: list[str]
    actions: list[dict[str, Any]]
    left: int | None


class MlTrial(Schema):
    offers: list[MlOffer]
    result: MlResult | None


def _rows(conversations):
    return [MlTalkRow(id=c.pk, slug=c.slug, title=c.title, steps=c.n_steps, persona=c.persona_id) for c in conversations]


def _persona(persona):
    talks = persona.conversations.annotate(n_steps=Count("steps")).order_by("title")
    return MlPersona(id=persona.pk, address=persona.address, name=persona.name, signature=persona.signature, note=persona.note,
                     conversations=_rows(talks))


def _talk(conversation):
    doc = authoring.export(conversation)
    return MlTalk(id=conversation.pk, doc=doc, problems=authoring.problems(doc))


def _persona_fields(persona, body):
    address = body.address.strip().lower()
    if "@" not in address:
        raise ValidationError({"address": ["Адрес вида имя@машина."]})
    if Persona.objects.filter(address=address).exclude(pk=persona.pk).exists():
        raise ValidationError({"address": ["Такой адрес уже есть."]})
    persona.address, persona.name, persona.signature, persona.note = address, body.name.strip(), body.signature, body.note
    persona.save()
    return _persona(persona)


@router.get("", response=list[MlPersona])
def index(request):
    return [_persona(persona) for persona in Persona.objects.order_by("address")]


@router.post("/personas", response=MlPersona)
def persona_create(request, body: MlPersonaIn):
    return _persona_fields(Persona(), body)


@router.put("/personas/{persona_id}", response=MlPersona)
def persona_update(request, persona_id: int, body: MlPersonaIn):
    return _persona_fields(get_object_or_404(Persona, pk=persona_id), body)


@router.delete("/personas/{persona_id}", response={204: None})
def persona_delete(request, persona_id: int):
    get_object_or_404(Persona, pk=persona_id).delete()
    return 204, None


@router.post("/conversations", response=MlTalkRow)
def talk_create(request, body: MlNewTalk):
    conversation = authoring.create(get_object_or_404(Persona, pk=body.persona), body.title, body.slug.strip())
    return MlTalkRow(id=conversation.pk, slug=conversation.slug, title=conversation.title, steps=1, persona=conversation.persona_id)


@router.get("/conversations/{talk_id}", response=MlTalk)
def talk_detail(request, talk_id: int):
    return _talk(get_object_or_404(Conversation, pk=talk_id))


@router.put("/conversations/{talk_id}", response=MlTalk)
def talk_update(request, talk_id: int, body: MlDoc):
    conversation = authoring.save(get_object_or_404(Conversation, pk=talk_id), body.dict())
    return _talk(conversation)


@router.delete("/conversations/{talk_id}", response={204: None})
def talk_delete(request, talk_id: int):
    get_object_or_404(Conversation, pk=talk_id).delete()
    return 204, None


@router.post("/check", response=list[MlProblem])
def check(request, body: MlDoc):
    return authoring.problems(body.dict())


@router.post("/try", response=MlTrial)
def trial(request, body: MlTry):
    return authoring.trial([v.dict() for v in body.variants], keys=body.keys, flags=body.flags, account=body.account, pick=body.pick,
                           typed=body.typed, used=body.used, attachment=body.attachment)


def _pick(item):
    letter = authoring.letter_view(item) if item.format == authoring.LETTER_FORMAT else {}
    return MlPick(slug=item.slug, label=item.name, format=item.format, subject=letter.get("subject", ""), text=letter.get("text", ""))


@router.get("/picks", response=MlPicks)
def picks(request, q: str = "", kind: str = ""):
    """Что можно выбрать в редакторе: объекты (письма, ключи, любые) по поиску, учётки, известные метки."""
    from filesystem.models import KEY_FORMAT, Item
    from machines.models import MachineProfile

    items = Item.objects.all()
    if kind == "letter":
        items = items.filter(format=authoring.LETTER_FORMAT)
    elif kind == "key":
        items = items.filter(format=KEY_FORMAT)
    if q.strip():
        items = items.filter(Q(slug__icontains=q.strip()) | Q(name__icontains=q.strip()))
    accounts = MachineProfile.objects.select_related("machine").order_by("machine__name", "login")[:200]
    flags = set()
    for need, deny, outcomes in Variant.objects.values_list("need_flags", "deny_flags", "outcomes"):
        flags |= set(need or []) | set(deny or [])
        flags |= {a.get("name", "") for actions in (outcomes or {}).values() for a in actions or [] if a.get("do") in ("flag", "unflag")}
    return MlPicks(
        items=[_pick(item) for item in items.order_by("slug")[:40]],
        accounts=[MlAccount(id=a.pk, label=f"{a.login}@{a.machine.label}") for a in accounts],
        flags=sorted(f for f in flags if f),
    )
