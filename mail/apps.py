from django.apps import AppConfig


class MailConfig(AppConfig):
    name = 'mail'

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from .models import Delivered, Message, MessageRead, Trashed
        from .pulse_cache import bump_version

        for model in (Message, Delivered, MessageRead, Trashed):
            post_save.connect(lambda **kw: bump_version(), sender=model, weak=False, dispatch_uid=f"mail-bump-{model.__name__}")
            post_delete.connect(lambda **kw: bump_version(), sender=model, weak=False, dispatch_uid=f"mail-bump-del-{model.__name__}")
