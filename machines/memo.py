"""Память одного запроса: то, что за запрос не меняется, читается из базы один раз.

Middleware открывает память в начале запроса и закрывает в конце. Вне запроса (скрипты, тесты без клиента) памяти нет, и каждый вызов
читает базу заново, как раньше. Настройки (места, группы, типы систем) в ходе запроса игрока меняются только админкой, то есть другим
запросом, поэтому внутри запроса им можно верить.
"""
import contextvars

_current = contextvars.ContextVar("request_memo", default=None)


def cached(key, factory):
    """Значение по ключу: считается один раз за запрос; вне запроса просто вызывает factory."""
    store = _current.get()
    if store is None:
        return factory()
    if key not in store:
        store[key] = factory()
    return store[key]


class MemoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current.set({})
        try:
            return self.get_response(request)
        finally:
            _current.reset(token)
