"""Версия содержимого вики: любое сохранение или удаление записи и неймспейса поднимает её, и общие кэши
(число записей в дереве) устаревают. Срок жизни записи кэша страхует массовые операции без сигналов."""
from django.core.cache import cache

WIKI_VERSION_KEY = "wiki:version"
WIKI_COUNTS_TTL = 600


def bump_version():
    try:
        cache.incr(WIKI_VERSION_KEY)
    except ValueError:
        cache.set(WIKI_VERSION_KEY, 1, None)
