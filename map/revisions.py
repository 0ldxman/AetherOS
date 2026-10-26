"""История и перенос сохранённых карт: снимки полей, откат, выгрузка и загрузка JSON."""
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import MapScene, MapSceneRevision

FIELDS = (
    "title", "base_date", "mode", "lat", "lon", "zoom", "bounds", "min_zoom", "max_zoom",
    "flat", "features", "key_condition",
)
KEEP_REVISIONS = 50


def snapshot(scene):
    """Поля сцены словарём, который можно положить в JSON."""
    data = {name: getattr(scene, name) for name in FIELDS}
    data["base_date"] = str(scene.base_date) if scene.base_date else None
    return data


def record_revision(scene, user=None):
    """Запомнить состояние сцены, если оно отличается от последнего снимка."""
    data = snapshot(scene)
    last = scene.revisions.first()
    if last is not None and last.data == data:
        return None
    revision = MapSceneRevision.objects.create(
        scene=scene, saved_by=user if getattr(user, "pk", None) else None, data=data
    )
    for old in scene.revisions.all()[KEEP_REVISIONS:]:
        old.delete()
    return revision


def apply_data(scene, data):
    """Положить поля из снимка или файла в сцену (без сохранения). Неизвестные ключи игнорируются."""
    for name in FIELDS:
        if name not in data:
            continue
        value = data[name]
        if name == "base_date":
            try:
                value = date.fromisoformat(value) if value else None
            except (TypeError, ValueError):
                raise ValidationError("base_date вида ГГГГ-ММ-ДД.")
        setattr(scene, name, value)
    return scene


def export_scenes(scenes):
    """Сцены в список словарей для файла."""
    return [{"slug": scene.slug, **snapshot(scene)} for scene in scenes]


@transaction.atomic
def import_scenes(items, user=None):
    """Создать или обновить сцены по слагу. Любая ошибка отменяет всё. -> (создано, обновлено)."""
    if not isinstance(items, list):
        raise ValidationError("Файл это список сцен.")
    created = updated = 0
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict) or not item.get("slug"):
            raise ValidationError(f"Сцена {number}: нужен slug.")
        scene = MapScene.objects.filter(slug=item["slug"]).first()
        is_new = scene is None
        scene = scene or MapScene(slug=item["slug"])
        try:
            apply_data(scene, item)
            scene.full_clean()
        except ValidationError as error:
            raise ValidationError(f"Сцена «{item['slug']}»: {'; '.join(error.messages)}")
        scene.save()
        record_revision(scene, user)
        created += is_new
        updated += not is_new
    return created, updated
