from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = "documents"
    verbose_name = "Документы"

    def ready(self):
        from documents import flatten, key_usage
        from documents.views import page_url
        from filesystem.content.rawview import flatten as file_flatten
        from filesystem.content.sources import Content
        from filesystem.content.sources import items as sources_items
        from secure import usage

        file_flatten.register(flatten.flatten)
        sources_items.document_window = lambda address: Content(url=page_url(address))
        usage.register(key_usage.key_usage)
