from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.test import RequestFactory

from wiki import views
from wiki.models import Document, Namespace

rf = RequestFactory()


def call(fn, *args):
    try:
        r = fn(rf.get("/"), *args)
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

        raise Rollback
except Rollback:
    print("Готово, тестовые данные откатены.")