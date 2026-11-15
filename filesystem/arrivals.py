"""Объект попал к игроку: событие object.got с тем, откуда он пришёл (для «Объект: Получен» в сценариях)."""
VIA = {"archive": "из письма или архива", "forum": "с форума", "net": "скачан с сервера", "xfer": "перенесён с машины",
           "join": "собран из частей", "key": "ключ в секретах", "scenario": "выдан сценарием"}


def got(view, path, item, source):
    """Сообщить, что объект item лёг игроку по пути path. Без игрока или объекта — ничего."""
    user = getattr(view, "user", None)
    if user is None or item is None:
        return
    from engine.events import emit

    emit("object.got", user, machine=view.machine, login=getattr(view, "login", "") or "", item=item.slug, path=path, via=source)
