"""Адрес файла для окон-вьюверов: по какому параметру запроса найти файл и вид машины, в котором он лежит.

Вьюверу (документ, текст, сырые байты) всё равно, откуда файл: из файлов игрока (?path=, терминал) или из раздела вики
(?wiki=, его вид машины на хосте). Каждое приложение называет свой параметр и само проверяет доступ; вьювер зовёт locate.
"""
from django.http import Http404
from django.utils.http import urlencode

_locators = {}


def register(param, locator):
    """locator(request, value) -> (запись, вид машины) или None, если файла нет или он не виден."""
    _locators[param] = locator


def locate(request):
    """(запись, вид машины) файла из адреса запроса. Нет адреса или файла: 404."""
    for param, locator in _locators.items():
        value = request.GET.get(param)
        if value is not None:
            found = locator(request, value)
            if found is None:
                raise Http404
            return found
    raise Http404


def address_of(request):
    """Адрес файла из запроса как словарь параметров (чтобы передать его дальше: окну, байтам, инфобоксу)."""
    return {param: request.GET[param] for param in _locators if param in request.GET}


def query(address, **extra):
    return urlencode({**address, **extra})
