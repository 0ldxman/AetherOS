"""Где в почте назван ключ: условия показа писем (их ищет secure.usage)."""
from django.urls import reverse

from mail.models import Message
from secure.access import condition_slugs
from secure.usage import Usage


def key_usage(slug):
    return [
        Usage("письмо", str(message), reverse("admin:mail_message_change", args=[message.pk]))
        for message in Message.objects.exclude(key_condition=None)
        if slug in condition_slugs(message.key_condition)
    ]


def key_conditions():
    return Message.objects.exclude(key_condition=None).values_list("key_condition", flat=True)
