"""Команда авторов: роли и авторы. Смотрят все авторы, правит только суперадмин (team.rights). Логика в team.members."""
import datetime as dt

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from team import members, rights
from team.models import Role

router = Router(tags=["team"])


class TeamSection(Schema):
    name: str
    label: str


class TeamAction(Schema):
    name: str
    label: str


class TeamRole(Schema):
    id: int
    name: str
    note: str
    sections: dict[str, str]     # раздел -> none|read|edit (у каждого раздела)
    actions: list[str]
    authors: int


class TeamRoleIn(Schema):
    name: str
    note: str = ""
    sections: dict[str, str] = {}
    actions: list[str] = []


class TeamAuthor(Schema):
    id: int
    username: str
    superuser: bool
    role: int | None
    last_login: dt.datetime | None


class TeamAuthorIn(Schema):
    role: int | None = None


class TeamCandidate(Schema):
    id: int
    username: str


class TeamOut(Schema):
    sections: list[TeamSection]
    actions: list[TeamAction]
    levels: dict[str, str]
    roles: list[TeamRole]
    authors: list[TeamAuthor]


def _role(role):
    return TeamRole(
        id=role.pk, name=role.name, note=role.note,
        sections={section: role.rights.get(section, rights.NONE) for section in rights.SECTIONS},
        actions=[action for action in rights.ACTIONS if action in role.actions],
        authors=role.users.filter(is_staff=True).count(),
    )


def _author(user):
    return TeamAuthor(id=user.pk, username=user.get_username(), superuser=user.is_superuser, role=user.role_id, last_login=user.last_login)


def _refused(call):
    try:
        return call()
    except members.TeamError as exc:
        raise HttpError(400, str(exc))
    except ValidationError as exc:
        raise exc


@router.get("", response=TeamOut)
def team(request):
    return TeamOut(
        sections=[TeamSection(name=name, label=label) for name, label in rights.SECTIONS.items()],
        actions=[TeamAction(name=name, label=label) for name, label in rights.ACTIONS.items()],
        levels=rights.LEVEL_LABELS,
        roles=[_role(role) for role in Role.objects.all()],
        authors=[_author(user) for user in members.authors()],
    )


@router.post("/roles", response=TeamRole)
def create_role(request, body: TeamRoleIn):
    return _role(members.save_role(Role(), body.name, body.note, body.sections, body.actions))


@router.put("/roles/{int:role_id}", response=TeamRole)
def update_role(request, role_id: int, body: TeamRoleIn):
    role = get_object_or_404(Role, pk=role_id)
    return _role(members.save_role(role, body.name, body.note, body.sections, body.actions))


@router.delete("/roles/{int:role_id}", response={204: None})
def delete_role(request, role_id: int):
    members.delete_role(get_object_or_404(Role, pk=role_id))
    return 204, None


@router.get("/candidates", response=list[TeamCandidate])
def candidates(request, q: str = ""):
    """Пользователи не из команды: кого можно сделать автором."""
    return [TeamCandidate(id=user.pk, username=user.get_username()) for user in members.find_users(q)]


@router.put("/authors/{int:user_id}", response=TeamAuthor)
def set_author(request, user_id: int, body: TeamAuthorIn):
    user = get_object_or_404(get_user_model(), pk=user_id)
    role = get_object_or_404(Role, pk=body.role) if body.role is not None else None
    return _author(_refused(lambda: members.set_author(request.user, user, role)))


@router.delete("/authors/{int:user_id}", response={204: None})
def remove_author(request, user_id: int):
    user = get_object_or_404(get_user_model(), pk=user_id, is_staff=True)
    _refused(lambda: members.remove_author(request.user, user))
    return 204, None


class TeamChange(Schema):
    id: int
    at: dt.datetime
    user: int | None
    username: str
    section: str
    section_label: str
    action: str
    action_label: str
    kind: str
    label: str
    summary: str
    link: str
    restorable: bool             # есть снимок удалённой сущности


@router.get("/changes", response=list[TeamChange])
def change_feed(request, author: int | None = None, section: str = "", before: int | None = None, limit: int = 50):
    """Лента изменений Студии: новые сверху, по автору и разделу, страницами по before."""
    from team import changes

    return [
        TeamChange(
            id=c.pk, at=c.at, user=c.user_id, username=c.username, section=c.section,
            section_label=rights.SECTIONS.get(c.section, "Команда" if c.section == rights.TEAM else c.section),
            action=c.action, action_label=changes.ACTION_LABELS.get(c.action, c.action), kind=c.kind, label=c.label,
            summary=c.summary, link=c.link if c.action != "delete" else "", restorable=c.snapshot is not None,
        )
        for c in changes.feed(author=author, section=section, before=before, limit=min(limit, 200))
    ]


class TeamLive(Schema):
    room: str
    kind: str
    label: str
    link: str
    people: list[str]            # кто сейчас на странице сущности
    dirty: bool                  # в черновике есть несохранённое
    editors: list[str]           # кто правил черновик
    updated_at: dt.datetime | None


@router.get("/live", response=list[TeamLive])
def live(request):
    """Сущности в работе: на странице кто-то есть или в черновике осталось несохранённое."""
    from team import changes, collab
    from team.models import Draft

    present = collab.live()
    drafts = {d.room: d for d in Draft.objects.filter(dirty=True)}
    rows = []
    for room in sorted(set(present) | set(drafts)):
        kind, label, link, _, _ = changes.describe(room)
        draft = drafts.get(room)
        rows.append(TeamLive(room=room, kind=kind, label=label, link=link, people=present.get(room, []),
                             dirty=draft is not None, editors=draft.editors if draft else [], updated_at=draft.updated_at if draft else None))
    rows.sort(key=lambda r: (not r.people, not r.dirty, r.label))
    return rows
