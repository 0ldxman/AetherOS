"""Сборка ключа из частей: рецепт на итоговом ключе, игрок складывает части командой kjoin.

Части — обычные ключи (объекты формата key): их выдают как любые ключи (блок в файле для kex, исход письма или ответчика).
Собрать можно, только если все части лежат в папке секретов записи; итоговый ключ ложится туда же.
"""
from django.db import transaction

from filesystem import keystore
from filesystem.models import KEY_FORMAT, Item
from secure.models import KeyPart, KeyRecipe


class RecipeError(ValueError):
    pass


def recipe_of(item):
    return KeyRecipe.objects.filter(result=item).prefetch_related("parts__item").first()


def parts_of(recipe):
    return [part.item for part in recipe.parts.all()]


def part_of(item):
    """Чьей частью является ключ: [(итоговый ключ, номер, всего)]."""
    found = []
    for part in KeyPart.objects.filter(item=item).select_related("recipe__result"):
        total = part.recipe.parts.count()
        number = list(part.recipe.parts.values_list("item_id", flat=True)).index(item.pk) + 1
        found.append((part.recipe.result, number, total))
    return found


@transaction.atomic
def set_parts(result, part_slugs, consume=False):
    """Задать части рецепта по слагам (порядок сохраняется). Пустой список — убрать рецепт."""
    if result.format != KEY_FORMAT:
        raise RecipeError("Собирать можно только ключ.")
    slugs = [slug for slug in dict.fromkeys(part_slugs) if slug]
    if not slugs:
        KeyRecipe.objects.filter(result=result).delete()
        return None
    if result.slug in slugs:
        raise RecipeError("Ключ не может быть частью самого себя.")
    items = {item.slug: item for item in Item.objects.filter(slug__in=slugs, format=KEY_FORMAT)}
    missing = [slug for slug in slugs if slug not in items]
    if missing:
        raise RecipeError(f"Нет ключей: {', '.join(missing)}.")
    if len(slugs) < 2:
        raise RecipeError("Частей нужно хотя бы две.")
    recipe, _ = KeyRecipe.objects.update_or_create(result=result, defaults={"consume": consume})
    recipe.parts.all().delete()
    KeyPart.objects.bulk_create([KeyPart(recipe=recipe, item=items[slug], position=number) for number, slug in enumerate(slugs)])
    return recipe


@transaction.atomic
def split(result, count, consume=False):
    """Создать count новых ключей-частей result.1 … result.N и сделать из них рецепт."""
    if not 2 <= count <= 12:
        raise RecipeError("Частей от 2 до 12.")
    made = []
    for number in range(1, count + 1):
        slug = f"{result.slug}.{number}"
        if Item.objects.filter(slug=slug).exists():
            raise RecipeError(f"Объект {slug} уже есть: выберите части вручную.")
        made.append(Item.objects.create(slug=slug, name=f"{result.name or result.slug} fragment {number}/{count}", format=KEY_FORMAT))
    return set_parts(result, [item.slug for item in made], consume)


def sources(item):
    """Откуда игрок получит ключ: [(вид, где)] — блок в файле, исход письма, исход ответчика эфира."""
    from filesystem.models import ItemKey

    found = [("файл", link.item.slug) for link in ItemKey.objects.filter(key=item).select_related("item")]
    try:
        from mail.models import Variant

        for variant in Variant.objects.select_related("step__conversation"):
            for actions in (variant.outcomes or {}).values():
                if any(action.get("do") == "key" and action.get("slug") == item.slug for action in actions or []):
                    found.append(("письмо", f"{variant.step.conversation} · шаг {variant.step.name}"))
                    break
    except Exception:                                       # noqa: BLE001 — почта необязательна
        pass
    from air.models import Responder

    for responder in Responder.objects.select_related("station"):
        if any(action.get("do") == "key" and action.get("slug") == item.slug for action in responder.actions or []):
            found.append(("ответчик", f"{responder.station.name} {responder.freq}"))
    return found


def join(view, machine, login, names):
    """Собрать ключ из файлов секретов names. Возвращает (итоговый ключ, путь, создан ли заново); RecipeError с текстом для игрока."""
    folder = keystore.secrets_dir(machine, login)
    if not folder:
        raise RecipeError("no secrets folder on this machine")
    held = dict(keystore.held(view, machine, login))           # имя файла -> слаг
    slugs = set()
    for name in names:
        base = name.rstrip("/").rsplit("/", 1)[-1]
        if base not in held:
            raise RecipeError(f"{name}: not in {folder}")
        slugs.add(held[base])
    if len(slugs) < 2:
        raise RecipeError("name at least two fragments")
    for recipe in KeyRecipe.objects.prefetch_related("parts__item").select_related("result"):
        if {part.item.slug for part in recipe.parts.all()} == slugs:
            path, fresh = keystore.put(view, machine, login, recipe.result)
            if recipe.consume:
                for name, slug in held.items():
                    if slug in slugs:
                        view.remove(f"{folder}/{name}")
            return recipe.result, path, fresh
    raise RecipeError("fragments do not fit")
