"""Хроника мира: обычный раздел, куда пишут триггеры действием forum в режиме append. Создание в один шаг из Студии."""
from django.db import transaction

from forum.models import Section
from world.models import WorldMoment, WorldTrigger

TOPIC = "World log"


def _trigger_name(moment):
    return f"chronicle-{moment.name}"[:64]


@transaction.atomic
def create(space, title="Chronicle", about="Network events as they happen."):
    """Раздел «только авторы» в корне пространства и по повторному триггеру на каждый момент мира: момент начался — запись в «World log».
    Существующие триггеры с тем же именем не трогаются. Возвращает (раздел, число новых триггеров)."""
    section = Section.objects.create(space=space, title=title[:120], about=about[:240], write="authors", create="authors",
                                     order=(Section.objects.filter(space=space, parent=None).count()))
    made = 0
    for moment in WorldMoment.objects.all():
        name = _trigger_name(moment)
        if WorldTrigger.objects.filter(name=name).exists():
            continue
        label = moment.title or moment.name
        WorldTrigger.objects.create(name=name, label=f"хроника: {moment.label or label}", condition=f"world:{moment.name}", repeat=True,
                                    was_true=False, actions=[{"do": "forum", "section": section.pk, "mode": "append", "title": TOPIC,
                                                              "text": f"{{time}} · {label} started."}])
        made += 1
    return section, made
