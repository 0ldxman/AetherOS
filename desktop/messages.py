"""Системные сообщения рабочего стола: ошибки и уведомления.

Приложения называют сообщение ключом (desktopAPI.error("access_denied", {object: ...})), а текст, код и
вид берутся из каталога операционной системы машины: у каждой системы свои коды и формулировки.
В текстах параметры пишутся как {object}; подставляет их браузер (текстом, не разметкой).
"""

DEFAULT_SYSTEM = "AETHER"

MESSAGES = {
    "AETHER": {
        "access_denied": {
            "kind": "error",
            "code": "AE-0403",
            "title": "Access denied",
            "text": "{object} is sealed. No matching key on this node.",
        },
        "not_found": {
            "kind": "error",
            "code": "AE-0404",
            "title": "Object not found",
            "text": "{object} is not present on this node.",
        },
        "unreachable": {
            "kind": "error",
            "code": "AE-0502",
            "title": "Node unreachable",
            "text": "No answer from the node. The link may be down.",
        },
        "timeout": {
            "kind": "warning",
            "code": "AE-0504",
            "title": "Link timed out",
            "text": "{object} did not answer in time.",
        },
        "failed": {
            "kind": "error",
            "code": "AE-0500",
            "title": "Operation failed",
            "text": "The request could not be completed.",
        },
        "uri_copied": {
            "kind": "info",
            "code": "",
            "title": "URI copied",
            "text": "{object}",
        },
        "mail_sent": {
            "kind": "info",
            "code": "",
            "title": "Message sent",
            "text": "Delivered through the intercom.",
        },
        "mail_new": {
            "kind": "info",
            "code": "",
            "title": "New message",
            "text": "{sender}: {subject}",
        },
    },
}


def catalog(system):
    """Сообщения системы машины; незнакомая система получает каталог по умолчанию."""
    return MESSAGES.get(system, MESSAGES[DEFAULT_SYSTEM])
