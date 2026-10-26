from django.apps import AppConfig
from django.db.models.signals import post_delete, post_save


class FilesystemConfig(AppConfig):
    name = 'filesystem'

    def ready(self):
        # реестр форматов запоминается на минуту; правка в админке сбрасывает запомненное сразу
        from filesystem.models import FileEncoding, FileFormat, FormatPart
        from filesystem.rawview.registry import invalidate

        for model in (FileFormat, FormatPart, FileEncoding):
            post_save.connect(invalidate, sender=model, dispatch_uid=f"rawview-invalidate-{model.__name__}")
            post_delete.connect(invalidate, sender=model, dispatch_uid=f"rawview-invalidate-{model.__name__}-del")
