"""Цепочки: шаги загадки по порядку, каждый — условие на факты игрока (ключи всех его учёток, flag:, world:).

Шаг считается пройденным, когда выполнены его условие и все шаги до него. Движок отмечает прохождение (ChainReach) при
каждом событии игрока и при открытии цепочки в Студии; первая отметка шага — кто прошёл его первым. Отчёт: воронка по шагам,
кто где стоит и сколько, у каких шагов разрыв (условие требует того, что негде взять).
"""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from engine.models import Chain, ChainReach, ChainStep


def _players():
    """Игроки для воронки: не авторы и не песочницы авторов, у кого есть учётка."""
    from machines.models import MachineProfile

    return get_user_model().objects.filter(is_staff=False, sandbox_of__isnull=True, pk__in=MachineProfile.objects.exclude(user=None).values("user"))


def player_facts(user):
    """Ключи всех учёток игрока и его метки."""
    from engine import facts
    from filesystem import keystore
    from filesystem.machine_view import view_for
    from machines.models import MachineProfile

    keys = set()
    profiles = MachineProfile.objects.filter(user=user).select_related("machine")
    for profile in profiles:
        if keystore.secrets_dir(profile.machine, profile.login):
            view = view_for(profile.machine, user, login=profile.login)
            keys.update(slug for _, slug in keystore.held(view, profile.machine, profile.login))
    return facts.of(user, keys)


def progress(steps, known):
    """Сколько шагов подряд с начала выполнено."""
    from secure.access import satisfied

    done = 0
    for step in steps:
        if not satisfied(step.condition, known):
            break
        done += 1
    return done


def update(user, chains=None):
    """Отметить пройденные игроком шаги. Возвращает число новых отметок."""
    if user is None or not getattr(user, "is_authenticated", False) or user.is_staff or getattr(user, "sandbox_of_id", None):
        return 0
    chains = list(chains if chains is not None else Chain.objects.filter(active=True).prefetch_related("steps"))
    if not chains:
        return 0
    known = player_facts(user)
    made = 0
    for chain in chains:
        steps = list(chain.steps.all())
        reached = set(ChainReach.objects.filter(step__chain=chain, user=user).values_list("step_id", flat=True))
        for step in steps[:progress(steps, known)]:
            if step.pk in reached:
                continue
            try:
                with transaction.atomic():
                    ChainReach.objects.create(step=step, user=user)
                made += 1
            except IntegrityError:
                pass
    return made


def refresh(chain):
    """Пересчитать цепочку для всех игроков (условия на мир меняются без события игрока)."""
    chain = Chain.objects.prefetch_related("steps").get(pk=chain.pk)
    players = _players()
    return sum(update(user, [chain]) for user in players)


def report(chain):
    """Воронка: по шагам — сколько прошли, кто первым, кто стоит на этом шаге (и с каких пор), есть ли разрыв."""
    from engine import links

    steps = list(chain.steps.all())
    reaches = {}
    for row in ChainReach.objects.filter(step__chain=chain).select_related("user").order_by("at", "id"):
        reaches.setdefault(row.step_id, []).append(row)
    players = list(_players())
    broken = {(row.kind, row.name): row.problem for row in links.analyze() if row.level == "error"}
    now = timezone.now()
    rows, standing = [], {}
    for player in players:                                   # на каком шаге стоит игрок: первый не пройденный
        position = 0
        last = None
        for step in steps:
            found = next((r for r in reaches.get(step.pk, []) if r.user_id == player.pk), None)
            if found is None:
                break
            position, last = position + 1, found.at
        standing.setdefault(position, []).append((player, last or player.date_joined))
    for index, step in enumerate(steps):
        done = reaches.get(step.pk, [])
        waiting = sorted(standing.get(index, []), key=lambda pair: pair[1])
        rows.append({
            "step": step, "reached": len(done), "first": (done[0].user, done[0].at) if done else None,
            "waiting": [{"user": user, "since": since, "days": (now - since).total_seconds() / 86400} for user, since in waiting],
            "breaks": [f"{kind}:{name}" if kind != "key" else name for kind, name in links.atoms(step.condition) if (kind, name) in broken],
        })
    finished = [user for user, _ in standing.get(len(steps), [])]
    return {"players": len(players), "steps": rows, "finished": finished}


@transaction.atomic
def save_steps(chain, steps):
    """Заменить шаги цепочки: [{"id"?, "title", "condition", "hint"}]. Шаги с прежним id сохраняют отметки прохождения."""
    keep = []
    for order, data in enumerate(steps):
        step = ChainStep.objects.filter(pk=data.get("id"), chain=chain).first() if data.get("id") else None
        step = step or ChainStep(chain=chain)
        step.order, step.title, step.condition, step.hint = order, data["title"], data.get("condition"), data.get("hint", "")
        step.save()
        keep.append(step.pk)
    ChainStep.objects.filter(chain=chain).exclude(pk__in=keep).delete()
