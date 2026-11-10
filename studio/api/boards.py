"""Доски команды: список, новая, переименовать, удалить; поиск сущностей для карточек. Логика в team.boards."""
import datetime as dt

from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from team import boards as logic
from team.models import Board

router = Router(tags=["boards"])


class BdRow(Schema):
    id: int
    title: str
    main: bool
    created_by: str
    updated_at: dt.datetime
    deletable: bool


class BdIn(Schema):
    title: str


class BdEntity(Schema):
    kind: str
    label: str
    link: str
    target: str                  # путь API сущности


def _row(board, user):
    return BdRow(id=board.pk, title=board.title, main=board.main, created_by=board.created_by.get_username() if board.created_by else "",
                 updated_at=board.updated_at, deletable=not board.main and (user.is_superuser or board.created_by_id == user.pk))


def _call(fn):
    try:
        return fn()
    except logic.BoardError as exc:
        raise HttpError(400, str(exc))


@router.get("", response=list[BdRow])
def board_list(request):
    return [_row(board, request.user) for board in logic.boards()]


@router.post("", response=BdRow)
def board_create(request, body: BdIn):
    return _row(_call(lambda: logic.create(request.user, body.title)), request.user)


@router.put("/{int:board_id}", response=BdRow)
def board_rename(request, board_id: int, body: BdIn):
    board = get_object_or_404(Board, pk=board_id)
    return _row(_call(lambda: logic.rename(board, body.title)), request.user)


@router.delete("/{int:board_id}", response={204: None})
def board_delete(request, board_id: int):
    board = get_object_or_404(Board, pk=board_id)
    _call(lambda: logic.delete(request.user, board))
    return 204, None


@router.get("/entities", response=list[BdEntity])
def board_entities(request, q: str = ""):
    """Сущности мира по названию: из них на доске делаются карточки со ссылкой."""
    return [BdEntity(**row) for row in logic.entities(q)]
