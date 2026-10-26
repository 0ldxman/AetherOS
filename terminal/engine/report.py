"""Что игрок получает из хуков событий файла (del, rcvr, cnt): строки и эффекты."""


def hook_report(fired):
    """Что игрок узнаёт из хуков (say и письма) и что делает браузер (kick, alert): (строки, эффекты или None)."""
    lines, effects, arrived = [], [], 0
    for item in fired:
        if item is None:
            continue
        lines += item.say
        effects += item.effects
        arrived += sum(1 for mail in item.mail if mail.delivered and mail.immediate)
    if arrived:
        lines.append(f"intercom: {arrived} new message{'s' if arrived != 1 else ''}")
    return lines, effects or None
