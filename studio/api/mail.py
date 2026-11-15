"""Почта: персонажи с адресами. Варианты ответа — возможности сценариев (graph/offers.py), их собирают в графе."""
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from mail.models import Persona

router = Router(tags=["mail"])


class MlPersona(Schema):
    id: int
    address: str
    name: str
    signature: str
    note: str


class MlPersonaIn(Schema):
    address: str
    name: str = ""
    signature: str = ""
    note: str = ""


def _persona(persona):
    return MlPersona(id=persona.pk, address=persona.address, name=persona.name, signature=persona.signature, note=persona.note)


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
