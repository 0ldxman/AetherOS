from django.apps import AppConfig


class MailConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mail"
    verbose_name = "Почта"

    def ready(self):
        from filesystem.content import locate

        locate.register("mail", locate_attachment)


def locate_attachment(request, path):
    """Адрес ?mail=: вложение письма в ящике того, кто сейчас за столом (filesystem.content.locate)."""
    from mail.boxes import box_for

    box = box_for(request)
    entry = box.attachment(path) if box is not None else None
    return None if entry is None else (entry, box.view)
