"""Сценарии переписки для редактора Студии: сценарий целиком как документ (шаги с вариантами и исходами), его сохранение,
проверка на ошибки и песочница (пройти вариант как игрок, ничего не меняя в мире).

Документ редактора:
    {"title", "slug", "note", "persona": id, "steps": [шаг]}
    шаг:     {"id"|None, "name", "x", "y", "opening", "letter": {"item": слаг|None, "subject", "text"}, "letter_delay", "variants": [вариант]}
    вариант: {"id"|None, "title", "mode", "text", "forward_of": слаг|None, "condition": текст условия, "need_flags", "deny_flags",
              "account": id|None, "closed", "attachment": {"kind": ""|item|key|signed, "slug"}, "max_attempts", "outcomes": {выход: [действие]}}
Письмо шага и действие «letter» пишутся прямо в редакторе (subject, text): при сохранении за ними создаётся или правится
объект формата msg, в мире остаётся только ссылка на него.
"""
import re
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from mail import letters, talk
from mail.models import Conversation, Step, Variant

LETTER_FORMAT = "msg"
ACTIONS = ("goto", "letter", "flag", "unflag", "key", "file", "hook", "bounce")
COLUMN, ROW = 340, 200                     # шаг сетки начальной раскладки карты


# ---- письма за шагами и действиями -------------------------------------------------------------------------------------

def letter_view(item):
    """Тема и текст письма объекта для редактора (заголовки From/To подставляет сохранение)."""
    if item is None:
        return {"item": None, "subject": "", "text": ""}
    parsed = letters.parse(item.body)
    return {"item": item.slug, "subject": parsed.subject, "text": parsed.body.strip("\n")}


def _letter_slug(base):
    from filesystem.models import Item

    base = (slugify(base) or "letter")[:56]
    slug, n = base, 1
    while Item.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


def write_letter(persona, data, fallback):
    """Объект письма по теме и тексту из редактора: существующий (по слагу) переписывается, иначе создаётся новый.
    Свои заголовки письма (X-…) сохраняются. Пустые тема и текст: письма нет (None)."""
    from filesystem.models import Item

    data = data or {}
    subject, text, slug = (data.get("subject") or "").strip(), (data.get("text") or "").rstrip(), data.get("item") or None
    if not subject and not text:
        return None
    item = Item.objects.filter(slug=slug).first() if slug else None
    sender, extra = persona.address, []
    if item is not None:                                  # письмо от чужого имени остаётся от чужого имени
        parsed = letters.parse(item.body)
        sender = parsed.sender or sender
        extra = [(name, value) for name, value in parsed.headers if name.lower() not in ("from", "to", "subject")]
    body = letters.compose([("From", sender), ("To", "{to}"), ("Subject", subject or "(no subject)"), *extra], text + "\n")
    if item is None:
        slug = _letter_slug(fallback)
        return Item.objects.create(slug=slug, name=f"{slug}.msg", format=LETTER_FORMAT, body=body)
    if item.body != body:
        item.body = body
        item.save(update_fields=["body"])
    return item


# ---- документ редактора -------------------------------------------------------------------------------------------------

def _condition_text(condition):
    from documents.markup.expr import SpoilerSyntaxError, format_expr

    if not condition:
        return ""
    try:
        return format_expr(condition)
    except SpoilerSyntaxError:
        return ""


def _attachment_view(attachment):
    for kind in ("item", "key", "signed"):
        if (attachment or {}).get(kind):
            return {"kind": kind, "slug": attachment[kind]}
    return {"kind": "", "slug": ""}


def _outcomes_view(outcomes):
    from filesystem.models import Item

    view = {}
    for socket, actions in (outcomes or {}).items():
        rows = []
        for action in actions or []:
            row = dict(action)
            if row.get("do") == "letter":
                row.update({k: v for k, v in letter_view(Item.objects.filter(slug=row.get("item")).first()).items() if k != "item"})
            rows.append(row)
        view[socket] = rows
    return view


def variant_view(variant):
    return {
        "id": variant.pk, "title": variant.title, "mode": variant.mode, "text": variant.text,
        "forward_of": variant.forward_of.slug if variant.forward_of_id else None,
        "condition": _condition_text(variant.condition), "need_flags": list(variant.need_flags or []),
        "deny_flags": list(variant.deny_flags or []), "account": variant.account_id, "closed": variant.closed,
        "attachment": _attachment_view(variant.attachment), "max_attempts": variant.max_attempts,
        "outcomes": _outcomes_view(variant.outcomes),
    }


def export(conversation):
    steps = list(conversation.steps.select_related("letter").prefetch_related("variants__forward_of"))
    doc = {
        "title": conversation.title, "slug": conversation.slug, "note": conversation.note, "persona": conversation.persona_id,
        "steps": [{
            "id": step.pk, "name": step.name, "x": step.x, "y": step.y, "opening": step.opening,
            "letter": letter_view(step.letter), "letter_delay": step.letter_delay,
            "variants": [variant_view(variant) for variant in step.variants.all()],
        } for step in steps],
    }
    if doc["steps"] and all(step["x"] == 0 and step["y"] == 0 for step in doc["steps"]):
        layout(doc["steps"])
    return doc


def _targets(step):
    for variant in step.get("variants") or []:
        for socket, actions in (variant.get("outcomes") or {}).items():
            for action in actions or []:
                if action.get("do") == "goto" and action.get("step"):
                    yield variant, socket, action["step"]


def layout(steps):
    """Начальная раскладка карты: колонки по удалённости от начала (шаги начала и первый шаг), в колонке по порядку."""
    by_name = {step["name"]: step for step in steps}
    first = next((step for step in steps if not step.get("opening")), None)
    starts = [step for step in steps if step.get("opening") or step is first] or steps[:1]
    column = {step["name"]: 0 for step in starts}
    queue = list(starts)
    while queue:
        step = queue.pop(0)
        for _, _, target in _targets(step):
            if target in by_name and target not in column:
                column[target] = column[step["name"]] + 1
                queue.append(by_name[target])
    last = max(column.values(), default=-1)
    rows = {}
    for step in steps:
        col = column.setdefault(step["name"], last + 1)
        row = rows.get(col, 0)
        rows[col] = row + 1
        step["x"], step["y"] = float(col * COLUMN), float(row * ROW)
    return steps


# ---- проверка -----------------------------------------------------------------------------------------------------------

def problems(doc):
    """Ошибки и предупреждения сценария (документа редактора, в том числе несохранённого черновика):
    [{"level": error|warning, "step": имя|None, "variant": номер|None, "text"}]."""
    from documents.markup.expr import SpoilerSyntaxError, parse_expr
    from filesystem.models import Item

    out = []

    def add(level, text, step=None, variant=None):
        out.append({"level": level, "step": step, "variant": variant, "text": text})

    steps = doc.get("steps") or []
    if not steps:
        add("error", "В сценарии нет шагов.")
        return out
    names = [step.get("name", "").strip() for step in steps]
    seen = set()
    for name in names:
        if not name:
            add("error", "У шага нет имени.")
        elif name in seen:
            add("error", f"Два шага с именем «{name}».", name)
        seen.add(name)
    if not SLUG_RE.fullmatch(doc.get("slug") or ""):
        add("error", "Идентификатор сценария: латиница, цифры, «-» и «_».")

    slugs = set()
    for step in steps:
        slugs |= {step.get("letter", {}).get("item")} if (step.get("letter") or {}).get("item") else set()
        for variant in step.get("variants") or []:
            for actions in (variant.get("outcomes") or {}).values():
                slugs |= {a.get("item") for a in actions or [] if a.get("item")} | {a.get("slug") for a in actions or [] if a.get("slug")}
            if variant.get("forward_of"):
                slugs.add(variant["forward_of"])
            if (variant.get("attachment") or {}).get("slug"):
                slugs.add(variant["attachment"]["slug"])
    known = set(Item.objects.filter(slug__in=slugs).values_list("slug", flat=True))

    targeted = {target for step in steps for _, _, target in _targets(step)}
    first = next((step.get("name") for step in steps if not step.get("opening")), None)
    for step in steps:
        name = step.get("name", "")
        if not step.get("opening") and name != first and name not in targeted:
            add("warning", "На этот шаг ничего не ведёт.", name)
        if (step.get("letter") or {}).get("item") and step["letter"]["item"] not in known:
            add("error", f"Письма «{step['letter']['item']}» нет.", name)
        if step.get("opening") and not step.get("variants"):
            add("warning", "Шаг начала без вариантов: игроку, который пишет первым, нечего ответить.", name)
        for index, variant in enumerate(step.get("variants") or []):
            where = {"step": name, "variant": index}
            if not (variant.get("title") or "").strip():
                add("error", "У варианта нет подписи.", **where)
            text = variant.get("text") or ""
            if re.search(r"\{\{\s*\}\}", text):
                add("error", "Пустой секрет {{}}.", **where)
            if re.search(r"\[\[\s*\|?\s*\]\]", text):
                add("error", "Пустой выбор [[]].", **where)
            if text.count("{{") != text.count("}}") or text.count("[[") != text.count("]]"):
                add("error", "Скобки {{ }} или [[ ]] не закрыты.", **where)
            if variant.get("mode") == Variant.Mode.FORWARD and not variant.get("forward_of"):
                add("error", "Пересылка: не выбрано, какое письмо переслать.", **where)
            if variant.get("forward_of") and variant["forward_of"] not in known:
                add("error", f"Письма «{variant['forward_of']}» нет.", **where)
            if (variant.get("condition") or "").strip():
                try:
                    parse_expr(variant["condition"])
                except SpoilerSyntaxError as error:
                    add("error", f"Условие: {error}", **where)
            attachment = variant.get("attachment") or {}
            if attachment.get("kind") and not attachment.get("slug"):
                add("error", "Вложение: не выбрано, что приложить.", **where)
            elif attachment.get("slug") and attachment["slug"] not in known:
                add("error", f"Вложение: объекта «{attachment['slug']}» нет.", **where)
            allowed = set(talk.sockets(text, _attachment_spec(attachment), variant.get("max_attempts") or 0))
            outcomes = variant.get("outcomes") or {}
            for socket, actions in outcomes.items():
                if actions and socket not in allowed:
                    add("warning", f"Исход «{socket}» никогда не сработает.", **where)
                for action in actions or []:
                    do = action.get("do")
                    if do not in ACTIONS:
                        add("error", f"Неизвестное действие «{do}».", **where)
                    elif do == "goto" and action.get("step") not in seen:
                        add("error", f"Переход на шаг «{action.get('step') or '?'}», которого нет.", **where)
                    elif do == "letter" and not action.get("item") and not (action.get("subject") or action.get("text")):
                        add("error", "Письмо в исходе пустое.", **where)
                    elif do == "letter" and action.get("item") and action["item"] not in known:
                        add("error", f"Письма «{action['item']}» нет.", **where)
                    elif do in ("key", "file") and (action.get("slug") or action.get("item")) not in known:
                        add("error", f"Объекта «{action.get('slug') or action.get('item') or '?'}» нет.", **where)
                    elif do in ("flag", "unflag") and not (action.get("name") or "").strip():
                        add("error", "Метка без имени.", **where)
                    elif do == "file" and not (action.get("path") or "").startswith("/"):
                        add("error", "Файл: путь должен начинаться с «/».", **where)
            if not any(outcomes.get(socket) for socket in allowed):
                add("warning", "У варианта нет исходов: ответ ни к чему не приведёт.", **where)
    return out


SLUG_RE = re.compile(r"[-a-zA-Z0-9_]+")


def _attachment_spec(view):
    view = view or {}
    return {view["kind"]: view.get("slug", "")} if view.get("kind") in ("item", "key", "signed") else {}


# ---- сохранение ---------------------------------------------------------------------------------------------------------

def _condition(text):
    from documents.markup.expr import SpoilerSyntaxError, parse_expr

    if not (text or "").strip():
        return None
    try:
        return parse_expr(text)
    except SpoilerSyntaxError as error:
        raise ValidationError({"condition": [str(error)]})


def _flags(values):
    return [name.strip() for name in values or [] if name and name.strip()]


def _outcomes(persona, conversation, step_name, outcomes):
    stored = {}
    for socket, actions in (outcomes or {}).items():
        rows = []
        for action in actions or []:
            do = action.get("do")
            if do not in ACTIONS:
                continue
            if do == "letter":
                item = write_letter(persona, action, f"{conversation.slug}-{step_name}-{socket.replace(':', '-')}")
                if item is None:
                    continue
                row = {"do": "letter", "item": item.slug}
                if action.get("delay"):
                    row["delay"] = int(action["delay"])
            else:
                keep = {"goto": ("step", "delay"), "flag": ("name",), "unflag": ("name",), "key": ("slug",), "file": ("item", "path"),
                        "hook": ("text",), "bounce": ()}[do]
                row = {"do": do, **{name: action[name] for name in keep if action.get(name) not in (None, "")}}
                if "delay" in row:
                    row["delay"] = int(row["delay"])
            rows.append(row)
        if rows:
            stored[socket] = rows
    return stored


@transaction.atomic
def save(conversation, doc):
    """Записать документ редактора в мир: шаги и варианты, которых в документе нет, удаляются, письма создаются и правятся."""
    from filesystem.models import Item
    from machines.models import MachineProfile
    from mail.models import Persona

    fatal = [p for p in problems(doc) if p["level"] == "error" and p["text"].startswith(("У шага нет имени", "Два шага", "Идентификатор"))]
    if fatal:
        raise ValidationError({"steps": [p["text"] for p in fatal]})
    if not (doc.get("title") or "").strip():
        raise ValidationError({"title": ["Нужно название."]})
    persona = Persona.objects.filter(pk=doc.get("persona")).first()
    if persona is None:
        raise ValidationError({"persona": ["Нужен персонаж."]})
    if Conversation.objects.filter(slug=doc["slug"]).exclude(pk=conversation.pk).exists():
        raise ValidationError({"slug": ["Такой идентификатор уже занят."]})
    conversation.title, conversation.slug, conversation.note, conversation.persona = doc["title"].strip(), doc["slug"], doc.get("note", ""), persona
    conversation.save()

    steps = doc.get("steps") or []
    existing = {step.pk: step for step in conversation.steps.all()}
    keep = {step.get("id") for step in steps if step.get("id") in existing}
    conversation.steps.exclude(pk__in=keep).delete()
    for pk in keep:                                         # имена освобождаются: шаги можно переставлять и менять местами
        Step.objects.filter(pk=pk).update(name=f"~{pk}")
    variants = {v.pk: v for v in Variant.objects.filter(step__conversation=conversation)}
    kept_variants = set()
    for order, data in enumerate(steps):
        step = existing.get(data.get("id")) or Step(conversation=conversation)
        step.name, step.order = data["name"].strip(), order
        step.x, step.y = float(data.get("x") or 0), float(data.get("y") or 0)
        step.opening = bool(data.get("opening"))
        step.letter_delay = max(0, int(data.get("letter_delay") or 0))
        step.letter = write_letter(persona, data.get("letter"), f"{conversation.slug}-{step.name}")
        step.save()
        for index, item in enumerate(data.get("variants") or []):
            variant = variants.get(item.get("id")) or Variant()
            variant.step, variant.order = step, index
            variant.title = (item.get("title") or "").strip() or "…"
            variant.mode = item.get("mode") if item.get("mode") in Variant.Mode.values else Variant.Mode.REPLY
            variant.text = item.get("text") or ""
            variant.forward_of = Item.objects.filter(slug=item.get("forward_of")).first() if item.get("forward_of") else None
            variant.condition = _condition(item.get("condition"))
            variant.need_flags, variant.deny_flags = _flags(item.get("need_flags")), _flags(item.get("deny_flags"))
            variant.account = MachineProfile.objects.filter(pk=item.get("account")).first() if item.get("account") else None
            variant.closed = item.get("closed") if item.get("closed") in Variant.Closed.values else Variant.Closed.MYSTERY
            variant.attachment = _attachment_spec(item.get("attachment"))
            variant.max_attempts = max(0, int(item.get("max_attempts") or 0))
            variant.outcomes = _outcomes(persona, conversation, step.name, item.get("outcomes"))
            variant.save()
            kept_variants.add(variant.pk)
    Variant.objects.filter(step__conversation=conversation).exclude(pk__in=kept_variants).delete()
    return conversation


def create(persona, title, slug):
    if not SLUG_RE.fullmatch(slug or ""):
        raise ValidationError({"slug": ["Латиница, цифры, «-» и «_»."]})
    if Conversation.objects.filter(slug=slug).exists():
        raise ValidationError({"slug": ["Такой идентификатор уже занят."]})
    conversation = Conversation.objects.create(persona=persona, title=title.strip() or slug, slug=slug)
    Step.objects.create(conversation=conversation, name="start", order=0)
    return conversation


# ---- песочница ----------------------------------------------------------------------------------------------------------

def trial(variants, *, keys=(), flags=(), account=None, pick=None, typed="", used=0, attachment=None):
    """Пройти шаг как игрок по черновику, ничего не меняя в мире.

    variants: варианты шага (как в документе редактора); keys и flags: что есть у игрока; account: учётка, с которой он пишет;
    pick: номер выбранного варианта; typed: набранный текст; used: сколько попыток варианта уже потрачено;
    attachment: слаг приложенного объекта. Ответ: что игрок видит и, если вариант выбран, чем кончится ответ."""
    from filesystem.models import Item

    keys, flags = set(keys or ()), set(flags or ())
    offers = []
    for index, data in enumerate(variants or []):
        try:
            condition = _condition(data.get("condition"))
        except ValidationError:
            condition = {"all": ["\0"]}                          # сломанное условие не откроется
        probe = SimpleNamespace(condition=condition, need_flags=_flags(data.get("need_flags")), deny_flags=_flags(data.get("deny_flags")),
                                account_id=data.get("account") or None)
        is_open = talk.available(probe, SimpleNamespace(pk=account) if account else None, keys, flags)
        shown = "open" if is_open else ("mystery" if data.get("closed", Variant.Closed.MYSTERY) == Variant.Closed.MYSTERY else "hidden")
        offers.append({"index": index, "title": data.get("title", ""), "shown": shown, "layout": talk.public(data.get("text", "")) if is_open else []})
    result = None
    if pick is not None and 0 <= pick < len(variants or []):
        data = variants[pick]
        if offers[pick]["shown"] != "open":
            result = {"kind": "closed", "verdict": "", "words": [], "sockets": [], "actions": [], "left": None}
        else:
            verdict = talk.check(data.get("text", ""), typed) if (data.get("text") or "").strip() else talk.Check("ok")
            if verdict.verdict == "mismatch":
                result = {"kind": "mismatch", "verdict": "mismatch", "words": [], "sockets": [], "actions": [], "left": None}
            else:
                need = _attachment_spec(data.get("attachment"))
                if verdict.verdict == "ok" and need:
                    item = Item.objects.filter(slug=attachment).first() if attachment else None
                    if not talk.attachment_fits(need, item):
                        verdict = talk.Check("wrong", verdict.words)
                turn = talk.decide(data.get("outcomes"), int(data.get("max_attempts") or 0), verdict, int(used or 0))
                result = {"kind": turn.kind, "verdict": verdict.verdict, "words": verdict.words, "sockets": turn.sockets,
                          "actions": turn.actions, "left": turn.left}
    return {"offers": offers, "result": result}
