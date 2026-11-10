from django.apps import AppConfig


class WikiConfig(AppConfig):
    name = 'wiki'

    def ready(self):
        import importlib

        from filesystem.content import locate
        from wiki.library import link_checker, locate_file

        importlib.import_module("documents.markup.lint").link_checker = link_checker   # имя lint в пакете занято функцией
        locate.register("wiki", locate_file)
