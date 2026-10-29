from django.apps import AppConfig


class TerminalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "terminal"

    def ready(self):
        from filesystem.content import locate
        from terminal.fsview.views import locate_player_file

        locate.register("path", locate_player_file)
