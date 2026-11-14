"""Переписка с персонажами: игрок отвечает не что угодно, а выбирает вариант и набирает его текст.

Сценарий (Conversation) состоит из шагов (Step). Попав на шаг, игрок получает письмо персонажа (если оно задано) и может
ответить одним из вариантов шага (Variant). В тексте варианта:
    {{секрет}}           игрок видит только длину и должен знать значение сам (пароль, имя);
    [[склад 7|склад 9]]  выбор слова: игрок набирает одно из них, от выбора зависит исход.
Сверка без учёта регистра, лишних пробелов и разницы ё/е.

Исходы варианта (outcomes) по ключам:
    ok              текст и секреты верны (если для выбранного слова нет своего исхода);
    word:<слово>    выбрано это слово;
    wrong           секрет неверен или вложение не то (попытка засчитана);
    exhausted       попытки варианта кончились.
Действия исхода — общий словарь движка (engine/actions.py) плюс свои: {"do": "goto", "step", "delay"} и {"do": "bounce"}.

Новое письмо на адрес персонажа даёт варианты текущего шага (или шага «начало переписки», если переписки ещё нет),
пересылка письма X даёт варианты-пересылки этого письма. Письмо на адрес, которого нет, возвращается от MAILER-DAEMON.
"""
import re
from dataclasses import dataclass, field

from django.db import transaction

from mail import letters
from mail.models import Conversation, Flag, Persona, Step, TalkState, Variant

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
            parts.append(("choice", [option.strip() for option in found.group(2).split("|") if option.strip()]))
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


# ---- кто что может ответить ---------------------------------------------------------------------------------------------

def flags_of(user):
    return set(Flag.objects.filter(user=user).values_list("name", flat=True)) if user is not None else set()


def available(variant, profile, keys, flags):
    from secure.access import satisfied

    if variant.condition and not satisfied(variant.condition, keys):
        return False
    if any(name not in flags for name in variant.need_flags or []):
        return False
    if any(name in flags for name in variant.deny_flags or []):
        return False
    return variant.account_id is None or (profile is not None and variant.account_id == profile.pk)


@dataclass
class Offer:
    variant: Variant
    open: bool


def _offered(steps, mode, profile, keys, flags, forward_of=None):
    offers = []
    for step in steps:
        for variant in step.variants.all():
            if variant.mode != mode or (mode == Variant.Mode.FORWARD and variant.forward_of_id != getattr(forward_of, "pk", None)):
                continue
            is_open = available(variant, profile, keys, flags)
            if is_open or variant.closed == Variant.Closed.MYSTERY:
                offers.append(Offer(variant, is_open))
    return offers


def _current_steps(user, persona):
    """Шаги, на которых игрок сейчас стоит с этим персонажем, и шаги начала тех переписок, которых ещё нет."""
    states = {s.conversation_id: s for s in TalkState.objects.filter(user=user, conversation__persona=persona).select_related("step")}
    steps = []
    for conversation in persona.conversations.prefetch_related("steps__variants"):
        state = states.get(conversation.pk)
        if state is not None and state.step is not None:
            steps.append(state.step)
        elif state is None:
            steps += [step for step in conversation.steps.all() if step.opening]
    return steps


def persona_of(address):
    return Persona.objects.filter(address=(address or "").strip().lower()).first()


def offers_for_reply(user, profile, keys, item):
    """Ответ на письмо персонажа (объект письма): варианты шага, на котором игрок стоит в этой переписке."""
    if item is None or user is None:
        return None, []
    step = Step.objects.filter(letter=item).select_related("conversation__persona").first()
    if step is None:
        return None, []
    state = TalkState.objects.filter(user=user, conversation=step.conversation).select_related("step").first()
    if state is None or state.step is None:
        return step.conversation.persona, []
    return step.conversation.persona, _offered([state.step], Variant.Mode.REPLY, profile, keys, flags_of(user))


def offers_for_address(user, profile, keys, address):
    persona = persona_of(address)
    if persona is None or user is None:
        return persona, []
    return persona, _offered(_current_steps(user, persona), Variant.Mode.REPLY, profile, keys, flags_of(user))


def offers_for_forward(user, profile, keys, address, item):
    persona = persona_of(address)
    if persona is None or user is None or item is None:
        return persona, []
    return persona, _offered(_current_steps(user, persona), Variant.Mode.FORWARD, profile, keys, flags_of(user), forward_of=item)


# ---- ход переписки ------------------------------------------------------------------------------------------------------

def enter(state, step, box, delay=0):
    """Игрок попадает на шаг: попытки сначала, письмо персонажа шага приходит (сразу или с задержкой)."""
    state.step = step
    state.attempts = {}
    state.save(update_fields=["step", "attempts", "updated_at"])
    if step.letter_id:
        box.queue(step.letter, step.letter_delay + delay)


def start(user, conversation, profile, delay=0):
    """Хук «mail <слаг сценария>»: переписка начинается с первого шага (по порядку, не «начало переписки»)."""
    from mail.boxes import Box

    first = conversation.steps.filter(opening=False).first() or conversation.steps.first()
    if first is None:
        return None
    state, _ = TalkState.objects.get_or_create(user=user, conversation=conversation, defaults={"profile": profile})
    state.profile = profile
    enter(state, first, Box.of_profile(profile, user), delay)
    return state


@dataclass
class Sent:
    kind: str                        # sent | ok | wrong | exhausted | bounced | mismatch | closed
    path: str = ""                   # письмо игрока в «отправленных»
    left: int | None = None          # сколько попыток осталось у варианта
    effects: list = field(default_factory=list)
    detail: str = ""


def _bounce(box, to, subject, reason):
    text = letters.compose(
        [("From", f"{DAEMON}@{box.machine.label}"), ("To", box.address), ("Subject", f"Undelivered Mail Returned to Sender: {subject}")],
        f"This is the mail system at host {box.machine.label}.\n\nI'm sorry to have to inform you that your message could not\n"
        f"be delivered to one or more recipients.\n\n<{to}>: {reason}",
    )
    box.put_text("inbox", "returned.msg", text)


def _attached_ok(variant, entry):
    return attachment_fits(variant.attachment, None if entry is None else entry.item)


def attachment_fits(need, item):
    """Подходит ли приложенный объект к требованию варианта ({"item"|"key"|"signed": слаг}; пустое: ничего не нужно)."""
    need = need or {}
    if not need:
        return True
    if item is None:
        return False
    if "item" in need:
        return item.slug == need["item"]
    if "key" in need:
        from filesystem.models import KEY_FORMAT

        return item.format == KEY_FORMAT and item.slug == need["key"]
    if "signed" in need:
        return item.signatures.filter(key__slug=need["signed"], valid=True).exists()
    return True


def _apply(actions, state, box, effects):
    """Исходы через движок (engine/actions.py); шаг переписки и возврат письма — свои действия почты."""
    from engine import actions as engine
    from engine.context import Ctx

    def goto(action, ctx):
        if state is None:
            return
        step = state.conversation.steps.filter(name=action.get("step")).first()
        if step is not None:
            enter(state, step, box, int(action.get("delay") or 0))

    def bounce(action, ctx):
        ctx.effects.append({"bounce": True})

    source = f"письмо {state.conversation.slug}" if state is not None else "ответчик"
    ctx = Ctx(source=source, user=box.user, box=box, session=True, host={"goto": goto, "bounce": bounce})
    effects += engine.run(actions, ctx)


def run_actions(actions, box):
    """Исходы вне переписки (ответчики эфира). Возвращает эффекты для браузера."""
    effects = []
    _apply(actions, None, box, effects)
    return effects


@dataclass
class Turn:
    kind: str                        # ok | wrong | exhausted
    sockets: list                    # какие исходы сработали (ok, word:<слово>, wrong, exhausted)
    actions: list
    left: int | None = None


def decide(outcomes, max_attempts, verdict, used=0):
    """Что случится после ответа: исход по сверке (verdict) и числу уже потраченных попыток варианта (used).
    Свои исходы выбранных слов важнее общего ok; exhausted без своих действий берёт действия wrong."""
    outcomes = outcomes or {}
    if verdict.verdict == "ok":
        sockets = [f"word:{word}" for word in verdict.words if outcomes.get(f"word:{word}")]
        actions = [action for socket in sockets for action in outcomes[socket]]
        if not sockets:
            sockets, actions = ["ok"], list(outcomes.get("ok", []))
        return Turn("ok", sockets, actions)
    spent = used + 1
    if max_attempts and spent >= max_attempts:
        socket = "exhausted" if outcomes.get("exhausted") else "wrong"
        return Turn("exhausted", [socket], list(outcomes.get(socket, [])), 0)
    return Turn("wrong", ["wrong"], list(outcomes.get("wrong", [])), max_attempts - spent if max_attempts else None)


def sockets(text, attachment=None, max_attempts=0):
    """Выходы варианта на карте: ok, по слову каждого выбора, wrong (если есть что угадать или приложить), exhausted."""
    out = ["ok"]
    secret = bool(attachment)
    for kind, value in segments(text):
        if kind == "choice":
            out += [f"word:{option}" for option in value if f"word:{option}" not in out]
        elif kind == "secret":
            secret = True
    if secret or max_attempts:
        out.append("wrong")
    if max_attempts:
        out.append("exhausted")
    return out


@transaction.atomic
def send(box, keys, *, to, subject="", typed="", variant=None, attachment=None, reply_item=None, forward_item=None):
    """Отправить письмо игрока. Его копия ложится в «отправленные», дальше решает адрес: персонаж (вариант и исходы),
    ящик учётки (письмо приходит туда в слое игрока) или никто (возврат от MAILER-DAEMON).

    attachment: файл вида машины игрока, приложенный к письму (или None)."""
    from machines.models import MachineProfile

    to = (to or "").strip().lower()
    if not to or "@" not in to:
        return Sent("mismatch", detail="no recipient")
    effects = []
    persona = persona_of(to)
    if variant is not None:
        # вариант должен быть среди тех, что игрок сейчас видит, и открыт
        if forward_item is not None:
            _, offers = offers_for_forward(box.user, box.profile, keys, to, forward_item)
        elif reply_item is not None:
            _, offers = offers_for_reply(box.user, box.profile, keys, reply_item)
            if not offers:
                _, offers = offers_for_address(box.user, box.profile, keys, to)
        else:
            _, offers = offers_for_address(box.user, box.profile, keys, to)
        match = next((offer for offer in offers if offer.variant.pk == variant.pk), None)
        if match is None or not match.open:
            return Sent("closed", detail="this answer is not available")
        if variant.step.conversation.persona_id != getattr(persona, "pk", None):
            return Sent("closed", detail="this answer is for another recipient")
        verdict = check(variant.text, typed) if variant.text.strip() else Check("ok")
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
    if persona is not None and variant is None:                     # вне сценария: письмо ждёт автора во входящих персонажа, игроку тишина
        from characters import inbox

        inbox.capture_mail(persona, box.user, box.address, subject, body, box.machine, path)

    if persona is None:
        account = MachineProfile.objects.filter(mail__iexact=to).select_related("machine").first()
        if account is None:
            _bounce(box, to, subject, "host or user unknown")
            return Sent("bounced", path)
        from mail.boxes import Box

        Box.of_profile(account, box.user).put_text("inbox", "letter.msg", letters.compose(headers, body))
        return Sent("sent", path)

    if variant is None:
        return Sent("sent", path)                             # персонаж молчит: на такое письмо ему нечего ответить

    conversation = variant.step.conversation
    state, _ = TalkState.objects.get_or_create(user=box.user, conversation=conversation, defaults={"profile": box.profile})
    if state.profile_id is None:
        state.profile = box.profile
    if state.step_id is None:
        state.step = variant.step                              # переписку начал сам игрок: он на шаге её начала
    state.save()

    if verdict.verdict == "ok" and not _attached_ok(variant, attachment):
        verdict = Check("wrong", verdict.words)

    used = (state.attempts or {}).get(str(variant.pk), 0)
    if verdict.verdict != "ok":
        state.attempts = {**(state.attempts or {}), str(variant.pk): used + 1}
        state.save(update_fields=["attempts", "updated_at"])
    turn = decide(variant.outcomes, variant.max_attempts, verdict, used)
    kind, actions, left = turn.kind, turn.actions, turn.left
    _apply(actions, state, box, effects)
    if any(effect.get("bounce") for effect in effects):
        _bounce(box, to, subject, "mailbox unavailable")
        effects = [effect for effect in effects if not effect.get("bounce")]
    return Sent(kind, path, left, effects)
