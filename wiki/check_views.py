import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.test import RequestFactory

from secure.models import Key
from users.models import UserKey
from wiki import views
from wiki.models import Document, Namespace

rf = RequestFactory()


def call(fn, *args, user=None, params=None):
    request = rf.get("/", params or {})
    request.user = user or AnonymousUser()
    try:
        r = fn(request, *args)
        return r.status_code, r.content.decode()
    except Http404:
        return 404, ""


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)


class Rollback(Exception):
    pass


try:
    with transaction.atomic():
        ns = Namespace.objects.create(name="_т_Разд", access="key_a")
        closed = Document.objects.create(
            namespace=ns, title="_т_Закрытая", body="секретный текст",
            direct_link="_t_link1",
        )
        open_doc = Document.objects.create(
            namespace=None, title="_т_Открытая", body="общий текст"
        )
        hidden = Document.objects.create(
            namespace=None, title="_т_Скрытая", visibility="key_b",
            body="тайна", direct_link="_t_link2",
        )

        code, html = call(views.resolve, "")
        check("главная: 200", code == 200)
        check("главная: раздел с замком виден", "_т_Разд" in html)
        check("главная: скрытая запись не видна", "_т_Скрытая" not in html)

        code, html = call(views.resolve, "_т_Разд")
        check("закрытый раздел: 403 и только название", code == 403 and "_т_Разд" in html)

        code, html = call(views.resolve, "_т_Разд/_т_Закрытая")
        check("запись в закрытом разделе: 403 без текста", code == 403 and "секретный текст" not in html)

        code, html = call(views.resolve, "_т_Открытая")
        check("открытая запись: 200 с текстом", code == 200 and "общий текст" in html)

        code, _ = call(views.resolve, "_т_Скрытая")
        check("скрытая по пути: 404", code == 404)

        code, html = call(views.direct, "_t_link2")
        check("скрытая по прямой ссылке: 200 с текстом", code == 200 and "тайна" in html)

        code, html = call(views.direct, "_t_link1")
        check("закрытая по прямой ссылке: 403 без названия", code == 403 and "_т_Закрытая" not in html)

        code, _ = call(views.direct, "нет_такой")
        check("несуществующая прямая ссылка: 404", code == 404)

        code, _ = call(views.resolve, "_т_Нет/_т_Открытая")
        check("несуществующий путь: 404", code == 404)

        for label, obj in [
            ("запись с названием раздела", Document(namespace=None, title="_т_Разд")),
            ("раздел с названием записи", Namespace(name="_т_Открытая")),
            ("корневой раздел go", Namespace(name="go")),
        ]:
            try:
                obj.full_clean()
                check(label + ": должна быть ошибка", False)
            except ValidationError:
                check(label + ": ошибка", True)

        # ---------- markdown и ::spoiler ----------

        key = Key.objects.create(slug="_t_key")
        player = get_user_model().objects.create_user("_t_player")
        UserKey.objects.create(user=player, key=key)
        Document.objects.create(
            namespace=None,
            title="_т_Со_спойлером",
            body="открытая часть\n\n**жирный**\n\n::spoiler _t_key\nтайный текст\n::",
            infobox="::spoiler _t_key\nтайный инфобокс\n::\n\nвидимый инфобокс",
        )

        code, html = call(views.resolve, "_т_Со_спойлером")
        check("markdown: жирный в html", code == 200 and "<strong>жирный</strong>" in html)
        check("тема: класс по типу записи", "doc--document" in html)
        check("гость: открытая часть есть, тайного текста нет",
              "открытая часть" in html and "тайный текст" not in html)
        check("гость: спойлер замазан", "spoiler--masked" in html and "█" in html)

        code, html = call(views.resolve, "_т_Со_спойлером", user=player)
        check("игрок с ключом: тайный текст виден", "тайный текст" in html and "spoiler--open" in html)
        check("игрок с ключом: ключ не в html", "_t_key" not in html)

        code, html = call(views.resolve, "_т_Со_спойлером", params={"infobox": 1})
        check("инфобокс у гостя: замазан", "тайный инфобокс" not in html and "видимый инфобокс" in html)
        check("инфобокс: вариант оформления", "md--infobox" in html)

        code, html = call(views.resolve, "_т_Со_спойлером", user=player, params={"infobox": 1})
        check("инфобокс у игрока с ключом: виден", "тайный инфобокс" in html)

        code, body = call(views.search, params={"q": "тайный"})
        check("поиск у гостя: по закрытому тексту не находит",
              code == 200 and json.loads(body)["rows"] == [])

        code, body = call(views.search, params={"q": "тайный"}, user=player)
        rows = json.loads(body)["rows"]
        check("поиск у игрока с ключом: находит", len(rows) == 1 and rows[0]["title"] == "_т_Со_спойлером")

        code, body = call(views.search, params={"q": "открытая часть"})
        check("поиск у гостя: по открытому тексту находит", len(json.loads(body)["rows"]) == 1)

        raise Rollback
except Rollback:
    print("Готово, тестовые данные откатены.")