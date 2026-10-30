from django.apps import AppConfig


class StudioConfig(AppConfig):
    name = "studio"
    verbose_name = "Студия"

    def ready(self):
        from filesystem.content import locate
        from studio.viewing import locate_item

        locate.register("item", locate_item)
