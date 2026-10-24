from django.apps import AppConfig
from django.db.models.signals import post_save


class WikiConfig(AppConfig):
    name = 'wiki'

    def ready(self):
        from .models import Document
        from .revisions import on_document_saved

        post_save.connect(
            on_document_saved,
            sender=Document,
            dispatch_uid="wiki_record_revision",
        )
