"""Учётки машины: карточка, создание, правка, удаление и токены.

Условие по ключам автор пишет выражением (secret_a and (door or not alarm)), как в спойлерах разметки; хранится оно в формате
secure.access. Пароль приходит открытым только при смене и сразу хешируется.
"""
import secrets
from datetime import datetime

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from documents.markup.expr import SpoilerSyntaxError, parse_expr
from machines.models import EntryPolicy, Machine, MachineProfile, MachineProfileToken, SceneScript
from studio.api.scenes import SceneChoice, choices
from secure.access import format_condition
from studio.api.machines import Policy, _policy

router = Router(tags=["accounts"])


class Token(Schema):
    id: int
    token: str
    usage: int
    max_usage: int | None
    expires_at: datetime | None
    created_at: datetime


class AccountOut(Schema):
    id: int
    login: str
    name: str
    freq: str
    mail: str
    groups: list[str]
    root: bool
    has_password: bool
    keys: str
    entry_policy: int | None
    policy: Policy | None
    ttl: int | None
    cooldown: int | None
    kick_message: str
    login_scene: str | None
    scene_library: list[SceneChoice]
    owner: str | None
    tokens: list[Token]


class AccountIn(Schema):
    login: str
    name: str = ""
    freq: str = "1"
    mail: str = ""
    groups: list[str] = []
    root: bool = False
    password: str | None = None          # None: не менять; "" вместе с clear_password: убрать пароль
    clear_password: bool = False
    keys: str = ""
    entry_policy: int | None = None
    ttl: int | None = None
    cooldown: int | None = None
    kick_message: str = ""
    login_scene: str | None = None       # слаг сцены после входа


class TokenIn(Schema):
    max_usage: int | None = None
    expires_at: datetime | None = None


def _profile(machine_id, account_id):
    return get_object_or_404(MachineProfile.objects.select_related("machine", "user", "entry_policy"), pk=account_id, machine_id=machine_id)


def _out(profile):
    return AccountOut(
        id=profile.pk, login=profile.login, name=profile.name, freq=f"{profile.freq:.3f}", mail=profile.mail, groups=list(profile.groups or []),
        root=profile.root, has_password=bool(profile.password_hash), keys=format_condition(profile.key_condition) if profile.key_condition else "",
        entry_policy=profile.entry_policy_id, policy=_policy(profile), ttl=profile.ttl, cooldown=profile.cooldown,
        kick_message=profile.kick_message, login_scene=profile.login_scene.slug if profile.login_scene_id else None,
        scene_library=choices(), owner=profile.user.get_username() if profile.user_id else None,
        tokens=[Token(id=t.pk, token=t.token, usage=t.usage, max_usage=t.max_usage, expires_at=t.expires_at, created_at=t.created_at)
                for t in profile.tokens.all()],
    )


def _apply(profile, body):
    errors = {}
    profile.login = body.login.strip()
    profile.name = body.name.strip() or profile.login
    profile.freq = body.freq.strip() or "1"
    profile.mail = body.mail.strip() or f"{profile.login}@{profile.machine.label}"      # как MachineProfile.save
    profile.groups = sorted({name.strip() for name in body.groups if name.strip()})
    profile.root = body.root
    if body.clear_password:
        profile.password_hash = ""
    elif body.password:
        profile.password_hash = make_password(body.password)
    try:
        profile.key_condition = parse_expr(body.keys) if body.keys.strip() else None
    except SpoilerSyntaxError as exc:
        errors["keys"] = [str(exc)]
    if body.entry_policy is not None and not EntryPolicy.objects.filter(pk=body.entry_policy).exists():
        errors["entry_policy"] = ["Такой политики нет."]
    profile.entry_policy_id = body.entry_policy
    profile.ttl, profile.cooldown, profile.kick_message = body.ttl, body.cooldown, body.kick_message
    profile.login_scene = SceneScript.objects.filter(slug=body.login_scene).first() if body.login_scene else None
    if body.login_scene and profile.login_scene is None:
        errors["login_scene"] = ["Такой сцены нет."]
    elif profile.login_scene is not None:
        from machines.world.slots import SLOTS

        found = profile.login_scene.problems(SLOTS["login.account"].params)
        if found:
            errors["login_scene"] = [f"Сцена не подходит: строка {n}: {t}" for n, t in found]
    try:
        profile.full_clean()
    except ValidationError as exc:
        errors.update(exc.message_dict)
    if errors:
        raise ValidationError(errors)
    profile.save()


@router.get("/{int:machine_id}/accounts/{int:account_id}", response=AccountOut)
def read(request, machine_id: int, account_id: int):
    return _out(_profile(machine_id, account_id))


@router.post("/{int:machine_id}/accounts", response=AccountOut)
def create(request, machine_id: int, body: AccountIn):
    profile = MachineProfile(machine=get_object_or_404(Machine, pk=machine_id))
    _apply(profile, body)
    return _out(_profile(machine_id, profile.pk))


@router.put("/{int:machine_id}/accounts/{int:account_id}", response=AccountOut)
def save(request, machine_id: int, account_id: int, body: AccountIn):
    profile = _profile(machine_id, account_id)
    _apply(profile, body)
    return _out(_profile(machine_id, account_id))


@router.delete("/{int:machine_id}/accounts/{int:account_id}")
def delete(request, machine_id: int, account_id: int):
    profile = _profile(machine_id, account_id)
    if profile.user_id is not None:
        raise ValidationError("Это рабочая учётка игрока: её нельзя удалить отсюда.")
    profile.delete()
    return {}


@router.post("/{int:machine_id}/accounts/{int:account_id}/tokens", response=Token)
def new_token(request, machine_id: int, account_id: int, body: TokenIn):
    profile = _profile(machine_id, account_id)
    token = MachineProfileToken.objects.create(
        profile=profile, token=f"tk-{secrets.token_urlsafe(9)}", max_usage=body.max_usage, expires_at=body.expires_at,
    )
    return Token(id=token.pk, token=token.token, usage=0, max_usage=token.max_usage, expires_at=token.expires_at, created_at=token.created_at)


@router.delete("/{int:machine_id}/accounts/{int:account_id}/tokens/{int:token_id}")
def drop_token(request, machine_id: int, account_id: int, token_id: int):
    get_object_or_404(MachineProfileToken, pk=token_id, profile=_profile(machine_id, account_id)).delete()
    return {}
