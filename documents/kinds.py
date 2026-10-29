"""Виды документов: формат файла -> тип страницы (по нему выбираются стили document/<тип>.css и значок)."""

# формат -> тип страницы
DOC_TYPES = {"doc": "doc", "scan": "scan", "snp": "web", "rec": "rec"}
DEFAULT_TYPE = "doc"


def doc_type(fmt):
    return DOC_TYPES.get(fmt, DEFAULT_TYPE)
