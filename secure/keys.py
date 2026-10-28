"""Реестр ключей: ключ это объект формата key (filesystem.models.KEY_FORMAT), его слаг входит в условия доступа."""


def key_items():
    from filesystem.models import KEY_FORMAT, Item

    return Item.objects.filter(format=KEY_FORMAT)


def key_slugs():
    return set(key_items().values_list("slug", flat=True))


def key_rows():
    """[{slug, description}] по слагу: описанием служит название объекта."""
    return [{"slug": row["slug"], "description": row["name"]} for row in key_items().order_by("slug").values("slug", "name")]
