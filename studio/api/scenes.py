"""Сцены: библиотека текстов на языке сцен (scenes/script.py), предпросмотр шагами для проигрывателя и события, к которым их привязывают."""
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from machines.models import SceneScript, SystemScene
from machines.models.scenes import resolve_script
from machines.world.dates import world
from machines.world.slots import SLOTS, all_params
from scenes.script import compile_script

router = Router(tags=["scenes"])

SAMPLE = {"host": "aether-core", "login": "ivan", "endpoint": "14.230 MHz", "freq": "14.230", "os": "AETHER", "reason": "Trace complete."}


class SceneRow(Schema):
    slug: str
    title: str
    bindings: int


class SlotInfo(Schema):
    slot: str
    label: str
    params: list[str]


class SceneBinding(Schema):
    system: str
    slot: str
    label: str


class SceneProblem(Schema):
    line: int
    text: str


class SceneOut(Schema):
    slug: str
    title: str
    body: str
    note: str
    errors: list[SceneProblem]
    bindings: list[SceneBinding]
    slots: list[SlotInfo]


class SceneIn(Schema):
    slug: str
    title: str = ""
    body: str = ""
    note: str = ""


class ScenePreviewIn(Schema):
    body: str
    slot: str = ""      # чьи подстановки брать: пусто, все слоты сразу


class ScenePreview(Schema):
    steps: list[dict]
    errors: list[SceneProblem]


def _scene(slug):
    return get_object_or_404(SceneScript, slug=slug)


def _out(script):
    return SceneOut(
        slug=script.slug, title=script.title, body=script.body, note=script.note,
        errors=[SceneProblem(line=n, text=t) for n, t in script.problems(all_params())],
        bindings=[SceneBinding(system=b.system_type.code, slot=b.slot, label=SLOTS[b.slot].label) for b in script.bindings.select_related("system_type") if b.slot in SLOTS],
        slots=[SlotInfo(slot=key, label=slot.label, params=list(slot.params)) for key, slot in SLOTS.items()],
    )


@router.get("", response=list[SceneRow])
def scenes(request):
    return [SceneRow(slug=s.slug, title=s.title, bindings=s.bindings.count()) for s in SceneScript.objects.all()]


@router.post("", response=SceneOut)
def create(request, body: SceneIn):
    script = SceneScript(slug=body.slug.strip(), title=body.title.strip(), body=body.body, note=body.note)
    script.full_clean()
    script.save()
    return _out(script)


@router.post("/preview", response=ScenePreview)
def preview(request, body: ScenePreviewIn):
    """Шаги сцены для проигрывателя студии: подстановки условные, «сейчас» как в мире."""
    names = SLOTS[body.slot].params if body.slot in SLOTS else all_params()
    scene, errors = compile_script(body.body, {name: SAMPLE.get(name, name) for name in names}, world().game_now, resolve_script)
    return ScenePreview(steps=scene.to_dict(), errors=[SceneProblem(line=n, text=t) for n, t in errors])


@router.get("/{slug}", response=SceneOut)
def read(request, slug: str):
    return _out(_scene(slug))


@router.put("/{slug}", response=SceneOut)
def save(request, slug: str, body: SceneIn):
    script = _scene(slug)
    script.slug, script.title, script.body, script.note = body.slug.strip(), body.title.strip(), body.body, body.note
    script.full_clean()
    script.save()
    return _out(script)


@router.delete("/{slug}")
def drop(request, slug: str):
    script = _scene(slug)
    if script.bindings.exists():
        raise ValidationError({"slug": ["Сцена назначена событиям ОС: сначала снимите её там."]})
    script.delete()
    return {"ok": True}
