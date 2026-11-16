"""Письмо всем игрокам по триггеру мира: в каждую учётку игрока на подходящей машине один раз, при следующем открытии её почты
(ленивая доставка). Сюжетные учётки его не получают."""
from world.models import WorldLetter, WorldLetterDelivery


def send_all(item, systems=(), machines=(), source="", condition=None):
    return WorldLetter.objects.create(item=item, systems=list(systems), machines=list(machines), source=source[:200], condition=condition or None)


def _fits(letter, machine):
    if letter.systems and (machine.system or "").upper() not in {s.upper() for s in letter.systems}:
        return False
    return not letter.machines or (machine.hostname or machine.name) in letter.machines


def deliver(box, keys=None):
    """Разложить игроку в ящик письма мира, которых у него ещё нет. Возвращает число новых.

    Письмо с условием приходит, когда ключи игрока (keys) его выполняют; до того оно ждёт и не считается доставленным."""
    from secure.access import satisfied

    if box is None or box.user is None or box.profile is None or box.profile.user_id is None:
        return 0                                         # только учётки игроков

    done = set(WorldLetterDelivery.objects.filter(profile=box.profile).values_list("letter_id", flat=True))
    made = 0
    for letter in WorldLetter.objects.exclude(pk__in=done).select_related("item"):
        if not _fits(letter, box.machine):
            continue
        if letter.condition and not satisfied(letter.condition, keys or set()):
            continue
        _, fresh = WorldLetterDelivery.objects.get_or_create(letter=letter, profile=box.profile)
        if fresh:
            box.deliver(letter.item)
            made += 1
    return made
