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


class StackAnswer(Schema):
    command: str
    text: str


class StackAction(Schema):
    name: str
    value: str = ""
    quoted: bool = False


class StackHook(Schema):
    event: str
    actions: list[StackAction]


class StackLayer(Schema):
    name: str
    values: dict[str, str]
    move: StackMove | None = None
    body: str = ""                               # ответы, хуки и комментарии слоя как текст
    answers: list[StackAnswer] | None = None     # ответы слоя на команды; null: тело правится только текстом
    hooks: list[StackHook] | None = None         # события слоя; null вместе с answers


class StackEvent(Schema):
    name: str
    title: str
    help: str


class StackActionKind(Schema):
    name: str
    title: str
    value_label: str
    example: str
    help: str
    text: bool


class StackHooks(Schema):
    events: list[StackEvent]
    actions: list[StackActionKind]
    commands: list[str]


class StackProblem(Schema):
    line: int
    message: str


class StackOut(Schema):
    steps: list[str]           # по слою: чем игрок его снимет
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
    steps: list[str]


class StackSource(Schema):
    text: str


@router.get("/catalog", response=list[StackKind])
def catalog(request):
    return stack.catalog()


@router.get("/hooks", response=StackHooks)
def hooks(request):
    return stack.hooks_catalog()


@router.post("/outline", response=StackOut)
def outline(request, body: StackSource):
    found = stack.outline(body.text)
    return StackOut(
        steps=stack.steps(found.layers), editable=found.editable, unsupported=found.unsupported, problems=[StackProblem(line=n, message=m) for n, m in found.problems],
        preamble=found.preamble,
        layers=[
            StackLayer(
                name=row.name, values=row.values, move=StackMove(kind=row.move[0], target=row.move[1]) if row.move else None, body=row.body,
                answers=None if row.answers is None else [StackAnswer(command=a.command, text=a.text) for a in row.answers],
                hooks=None if row.hooks is None else [
                    StackHook(event=h.event, actions=[StackAction(name=a.name, value=a.value, quoted=a.quoted) for a in h.actions]) for h in row.hooks
                ],
            )
            for row in found.layers
        ],
    )


@router.post("/build", response=StackText)
def build(request, body: StackIn):
    layers = [
        stack.OutlineLayer(
            name=row.name, values=row.values, move=(row.move.kind, row.move.target) if row.move else None, body=row.body,
            answers=None if row.answers is None else [stack.Answer(a.command, a.text) for a in row.answers],
            hooks=None if row.hooks is None else [stack.Hook(h.event, [stack.Action(a.name, a.value, a.quoted) for a in h.actions]) for h in row.hooks],
        )
        for row in body.layers
    ]
    return StackText(text=stack.build(body.preamble, layers), steps=stack.steps(layers))
