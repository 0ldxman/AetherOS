"""Конструктор слоёв защиты: каталог слоёв и перевод текста стека в структуру и обратно. Логика в filesystem.layers.outline."""
from ninja import Router, Schema

from filesystem.layers import outline as stack

router = Router(tags=["layers"])


class StackParam(Schema):
    name: str
    label: str
    type: str                  # str | int | float | bool
    required: bool
    positional: bool
    unlock: bool
    help: str
    default: str | None


class StackKind(Schema):
    name: str
    title: str
    summary: str
    params: list[StackParam]


class StackMove(Schema):
    kind: str                  # rename | copy
    target: str


class StackLayer(Schema):
    name: str
    values: dict[str, str]
    move: StackMove | None = None
    body: str = ""             # ответы, хуки и комментарии слоя как текст


class StackProblem(Schema):
    line: int
    message: str


class StackOut(Schema):
    editable: bool
    unsupported: str
    problems: list[StackProblem]
    preamble: str
    layers: list[StackLayer]


class StackIn(Schema):
    preamble: str = ""
    layers: list[StackLayer]


class StackText(Schema):
    text: str


class StackSource(Schema):
    text: str


@router.get("/catalog", response=list[StackKind])
def catalog(request):
    return stack.catalog()


@router.post("/outline", response=StackOut)
def outline(request, body: StackSource):
    found = stack.outline(body.text)
    return StackOut(
        editable=found.editable, unsupported=found.unsupported, problems=[StackProblem(line=n, message=m) for n, m in found.problems],
        preamble=found.preamble,
        layers=[
            StackLayer(name=row.name, values=row.values, move=StackMove(kind=row.move[0], target=row.move[1]) if row.move else None, body=row.body)
            for row in found.layers
        ],
    )


@router.post("/build", response=StackText)
def build(request, body: StackIn):
    layers = [
        stack.OutlineLayer(name=row.name, values=row.values, move=(row.move.kind, row.move.target) if row.move else None, body=row.body)
        for row in body.layers
    ]
    return StackText(text=stack.build(body.preamble, layers))
