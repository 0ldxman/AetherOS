"""Переписка с персонажами: игрок отвечает не что угодно, а выбирает вариант и набирает его текст.

Варианты — возможности канала «письмо» (graph/offers.py: сущность «Возможность», открывает «Возможность: Открыть»):
ответ на письмо, новое письмо на адрес персонажа, пересылка письма. В тексте варианта:
    {{секрет}}               игрок видит только длину и должен знать значение сам (пароль, имя);
    [[склад: 7|9]]           развилка: игрок набирает одно из слов; имя до «: » — выход «Использована» с выбранным словом.
Сверка без учёта регистра, лишних пробелов и разницы ё/е. Не тот текст — письмо не уходит; верный текст с неверным секретом
или не тем вложением — неверный ответ. Чем кончилось — событие offer.used («Возможность: Использована»).
Письмо без варианта ждёт автора во входящих персонажа; письмо на адрес, которого нет, возвращается от MAILER-DAEMON.
"""
import re
from dataclasses import dataclass, field

from django.db import transaction

from mail import letters
from mail.models import Persona

TOKEN = re.compile(r"\{\{(.+?)\}\}|\[\[(.+?)\]\]", re.DOTALL)
DAEMON = "MAILER-DAEMON"


# ---- текст для набора ---------------------------------------------------------------------------------------------------

def segments(text):
    """[("text", строка) | ("secret", значение) | ("choice", [варианты])]."""
    parts, last = [], 0
    text = (text or "").replace("\r\n", "\n")
    for found in TOKEN.finditer(text):
        if found.start() > last:
            parts.append(("text", text[last:found.start()]))
        if found.group(1) is not None:
            parts.append(("secret", found.group(1)))
        else:
            from graph.offers import fork

            parts.append(("choice", fork(found.group(2))[1]))
        last = found.end()
    if last < len(text):
        parts.append(("text", text[last:]))
    return parts


def public(text):
    """Что видит браузер: текст, длины секретов (без значений) и варианты слова."""
    return [{"text": value} if kind == "text" else {"hidden": len(value)} if kind == "secret" else {"choices": value}
            for kind, value in segments(text)]


def norm(text):
    return " ".join((text or "").replace("ё", "е").replace("Ё", "Е").casefold().split())


@dataclass
class Check:
    verdict: str                      # ok | wrong | mismatch
    words: list = field(default_factory=list)


def check(template, typed):
    """Сверить набранное с текстом варианта: mismatch (набран не тот текст), wrong (секрет неверен) или ok, и выбранные слова."""
    parts = segments(template)
    pattern, secrets = [], []
    for kind, value in parts:
        if kind == "text":
            piece = norm(value)
            if piece:
                pattern.append(re.escape(piece))
        elif kind == "secret":
            pattern.append("(.+?)")
            secrets.append(value)
        else:
            pattern.append("(" + "|".join(re.escape(norm(option)) for option in sorted(value, key=len, reverse=True)) + ")")
    found = re.fullmatch(r"\s*".join(pattern), norm(typed), re.DOTALL) if pattern else None
    if found is None:
        return Check("ok" if not pattern and not norm(typed) else "mismatch")
    groups, words, right, at = found.groups(), [], True, 0
    for kind, value in parts:
        if kind == "secret":
            right = right and norm(groups[at]) == norm(value)
            at += 1
        elif kind == "choice":
            words.append(next((option for option in value if norm(option) == groups[at]), groups[at]))
            at += 1
    return Check("ok" if right else "wrong", words)


# ---- что игрок может написать -------------------------------------------------------------------------------------------

def persona_of(address):
    return Persona.objects.filter(address=(address or "").strip().lower()).first()


def _addressed(spec, to, persona):
    """«Кому» варианта: адреса (с @) и коды персонажей (любой адрес персонажа)."""
    code = (getattr(getattr(persona, "character", None), "code", "") or "").lower()
    return any(one == to if "@" in one else bool(code) and one == code for one in spec.get("to") or [])


def _same_file(want, user, host, item, path):
    """Подходит ли файл ящика под «В ответ на» / «Что переслать» / «Вложение»: размещение «игрок@машина:/путь» — этот файл,
    иначе слаг объекта — любая его копия."""
    want = str(want or "").strip()
    if ":/" in want:
        from graph.offers import placement_of

        return bool(path) and placement_of(user, host, path).lower() == want.lower()
    return item is not None and item.slug == want


def offers_for(box, mode, to, item=None, path=""):
    """Варианты для ящика: mode reply (item, path — письмо, на которое отвечают), new или forward (что пересылают)."""
    from graph import offers

    if box.user is None:
        return []
    to = (to or "").strip().lower()
    persona = persona_of(to)
    host = getattr(box.machine, "hostname", "")
    found = []
    for view in offers.visible(box.user, host, box.login, "mail"):
        spec = view.spec
        if spec.get("mode", "reply") != mode or not _addressed(spec, to, persona):
            continue
        if mode == "reply" and spec.get("reply_to") and not _same_file(spec["reply_to"], box.user, host, item, path):
            continue
        if mode == "forward" and not _same_file(spec.get("forward_of"), box.user, host, item, path):
            continue
        found.append(view)
    return found


def offers_to_answer(box, to, reply_item=None, forward_item=None, reply_path="", forward_path=""):
    """Что игрок видит в наборе: пересылка, ответ (если на письмо вариантов нет — варианты нового письма) или новое письмо."""
    if forward_item is not None or forward_path:
        return offers_for(box, "forward", to, forward_item, forward_path)
    if reply_item is not None or reply_path:
        return offers_for(box, "reply", to, reply_item, reply_path) or offers_for(box, "new", to)
    return offers_for(box, "new", to)


# ---- отправка -----------------------------------------------------------------------------------------------------------

@dataclass
class Sent:
    kind: str                        # sent | ok | wrong | bounced | mismatch | closed
    path: str = ""                   # письмо игрока в «отправленных»
    effects: list = field(default_factory=list)
    detail: str = ""


def _bounce(box, to, subject, reason):
    text = letters.compose(
        [("From", f"{DAEMON}@{box.machine.label}"), ("To", box.address), ("Subject", f"Undelivered Mail Returned to Sender: {subject}")],
        f"This is the mail system at host {box.machine.label}.\n\nI'm sorry to have to inform you that your message could not\n"
        f"be delivered to one or more recipients.\n\n<{to}>: {reason}",
    )
    box.put_text("inbox", "returned.msg", text)


def attachment_fits(spec, box, attachment):
    """Подходит ли вложение к варианту. «Вложение» — объекты или размещения (любое из списка); «Сам файл» — этот объект
    (или этот файл), «Подписан им» — документ, подписанный этим ключом. Пусто — ничего не нужно."""
    wants = spec.get("attach") or []
    if not wants:
        return True
    if attachment is None:
        return False
    host = getattr(box.machine, "hostname", "")
    item = attachment.item
    if spec.get("attach_mode") != "signed":
        return any(_same_file(want, box.user, host, item, attachment.path) for want in wants)
    keys = {_key_slug(want) for want in wants} - {""}
    return item is not None and item.signatures.filter(key__slug__in=keys, valid=True).exists()


def _key_slug(want):
    """Слаг ключа: из размещения — объект этого файла, иначе как есть."""
    want = str(want or "").strip()
    if ":/" not in want:
        return want
    from filesystem.copies import at
    from graph.entities import parse_placement

    found = parse_placement(want)
    copy = at(*found) if found is not None else None
    return getattr(getattr(copy, "item", None), "slug", "") or ""


def run_actions(actions, box):
    """Действия движка вне сценариев (ответчики эфира). Возвращает эффекты для браузера."""
    from engine import actions as engine
    from engine.context import Ctx

    return engine.run(actions, Ctx(source="ответчик", user=box.user, box=box, session=True))


@transaction.atomic
def send(box, *, to, subject="", typed="", offer=None, attachment=None, reply_item=None, forward_item=None, reply_path="", forward_path=""):
    """Отправить письмо игрока. Его копия ложится в «отправленные», дальше решает адрес: персонаж (вариант — возможность offer,
    «слаг:нода»), ящик учётки (письмо приходит туда в слое игрока) или никто (возврат от MAILER-DAEMON).

    attachment: файл вида машины игрока, приложенный к письму (или None)."""
    from machines.models import MachineProfile

    to = (to or "").strip().lower()
    if not to or "@" not in to:
        return Sent("mismatch", detail="no recipient")
    persona = persona_of(to)
    view = verdict = None
    if offer:
        view = next((one for one in offers_to_answer(box, to, reply_item, forward_item, reply_path, forward_path) if one.key == offer), None)
        if view is None or not view.open:
            return Sent("closed", detail="this answer is not available")
        verdict = check(view.spec.get("text", ""), typed) if str(view.spec.get("text") or "").strip() else Check("ok")
        if verdict.verdict == "mismatch":
            return Sent("mismatch", detail="the text does not match")

    headers = [("From", box.address), ("To", to), ("Subject", subject or "(no subject)")]
    if attachment is not None:
        headers.append(("X-Attachment", attachment.path))
    if forward_item is not None:
        headers.append(("X-Forwarded", forward_item.slug or str(forward_item.pk)))
    body = typed
    if forward_item is not None:
        body = f"{typed}\n\n---------- Forwarded message ----------\n{forward_item.body}".strip()
    path = box.put_text("sent", "letter.msg", letters.compose(headers, body), read=True)
    from engine.events import emit

    if persona is not None and persona.character_id is not None:
        emit("character.wrote", box.user, machine=box.machine, login=box.login, character=persona.character.code, channel="mail",
             subject=subject, text=body, offer=view.key if view is not None else "")
    if persona is not None and view is None:                       # вне вариантов: письмо ждёт автора во входящих персонажа
        from characters import inbox

        inbox.capture_mail(persona, box.user, box.address, subject, body, box.machine, path)

    if persona is None:
        account = MachineProfile.objects.filter(mail__iexact=to).select_related("machine").first()
        if account is None:
            _bounce(box, to, subject, "host or user unknown")
            return Sent("bounced", path)
        from mail.boxes import Box

        Box.of_profile(account, box.user).put_text("inbox", "letter.msg", letters.compose(headers, body))
    if view is None:
        return Sent("sent", path)

    if verdict.verdict == "ok" and not attachment_fits(view.spec, box, attachment):
        verdict = Check("wrong", verdict.words)
    from graph import offers

    kind = offers.settle(view, box.user, verdict.verdict == "ok")
    offers.used(view, box.user, kind, machine=box.machine, login=box.login, words=verdict.words, text=body[:500], to=to,
                placement=offers.placement_of(box.user, getattr(box.machine, "hostname", ""), path))
    return Sent(kind, path)
