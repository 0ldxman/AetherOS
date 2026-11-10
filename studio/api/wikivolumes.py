"""Разделы вики приложения: строки volume файла .app. Хосты для выбора и проверка «откроется ли раздел» (игрок причину отказа не видит).

Проверка в wiki.library (check_line): та же логика, что строит разделы у игрока."""
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from filesystem.appfile import VolumeLine
from machines.models import Machine
from wiki import library

router = Router(tags=["wiki-volumes"])


class WvAccount(Schema):
    login: str
    freq: str


class WvHost(Schema):
    hostname: str
    label: str
    exports: list[str]
    accounts: list[WvAccount]


class WvLine(Schema):
    host: str = ""
    path: str
    title: str = ""
    user: str = ""


class WvCheckIn(Schema):
    lines: list[WvLine]
    machine: int | None = None       # с какой машины проверять строки без хоста


class WvResult(Schema):
    ok: bool
    reason: str
    message: str
    title: str                       # как раздел будет называться
    pages: int                       # страниц, которые учётка вправе читать
    closed: int                      # файлов, закрытых правами
    duplicate: bool                  # то же название у другого раздела: останется один


@router.get("/hosts", response=list[WvHost])
def hosts(request):
    """Машины, к которым можно подключиться: имя хоста, что он отдаёт и под какими учётками можно войти."""
    result = []
    for machine in Machine.objects.prefetch_related("exports", "profiles").order_by("hostname"):
        result.append(WvHost(
            hostname=machine.hostname, label=machine.label, exports=[e.path for e in machine.exports.all()],
            accounts=[WvAccount(login=p.login, freq=str(p.freq)) for p in machine.profiles.all() if p.user_id is None],
        ))
    return result


@router.post("/check", response=list[WvResult])
def check(request, body: WvCheckIn):
    machine = get_object_or_404(Machine, pk=body.machine) if body.machine else None
    results = []
    for line in body.lines:
        spec = VolumeLine(line.host.strip(), "/" + line.path.strip().strip("/") if line.path.strip().strip("/") else "/", line.title.strip(), line.user.strip())
        if spec.host == "" and machine is None:
            results.append({"ok": False, "reason": "no_machine", "message": "Для своей машины выберите, на какой машине проверять.", "title": spec.title or spec.path, "pages": 0, "closed": 0})
            continue
        results.append(library.check_line(machine or Machine(pk=0, hostname="", name=""), spec))
    titles = [r["title"].casefold() for r in results]
    return [WvResult(**r, duplicate=titles.count(r["title"].casefold()) > 1) for r in results]
