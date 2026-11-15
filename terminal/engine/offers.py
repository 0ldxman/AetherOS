"""Скрытые команды — возможности сценариев (graph/offers.py, канал «команда терминала»). Команду, которой у ОС нет, игрок
может ввести, пока возможность открыта; настоящие команды она не перекрывает. Аргументы сверяются, как текст варианта письма
(mail.talk.check: {{секрет}}, [[слово|другое]]); пустой шаблон принимает любые. Чем кончилось — событие offer.used."""
from terminal.engine.result import CommandResult


def _fill(text, name, args, left):
    return (text or "").replace("{command}", name).replace("{args}", args).replace("{left}", "" if left is None else str(left))


def run(session, context, parsed):
    """Ответ скрытой команды или None (такой возможности у игрока нет)."""
    from graph import offers
    from mail.talk import Check, check

    user = getattr(session, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    host, login = context.machine.hostname or "", getattr(context.view, "login", "") or ""
    name = parsed.name
    found = [view for view in offers.visible(user, host, login, "command")
             if view.open and view.spec.get("command") == name and (not view.spec.get("machines") or host.lower() in view.spec["machines"])]
    if not found:
        return None
    args = " ".join(parsed.args)
    for view in found:
        template = str(view.spec.get("text") or "")
        verdict = check(template, args) if template.strip() else Check("ok")
        if verdict.verdict != "mismatch":
            break
    else:
        return CommandResult(f"{name}: invalid arguments", 2)
    result, left = offers.attempt(view, user, verdict.verdict == "ok")
    offers.used(view, user, result, machine=context.machine, login=login, left=left, words=verdict.words, text=args[:300], command=name)
    if result == "ok":
        return CommandResult(_fill(view.spec.get("reply_ok"), name, args, left), 0)
    if result == "exhausted":
        return CommandResult(f"{name}: locked", 1)
    return CommandResult(_fill(view.spec.get("reply_wrong") or "{command}: access denied", name, args, left), 1)
