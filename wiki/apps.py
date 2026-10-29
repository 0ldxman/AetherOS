from django.apps import AppConfig
from django.db.models.signals import post_delete, post_save


class WikiConfig(AppConfig):
    name = 'wiki'

    def ready(self):
        from wiki.versioning import bump_version

        from filesystem.models import Item, Placement, Volume
        from machines.models import Export, MachineMount

        for model in (Item, Placement, Volume, MachineMount, Export):
            post_save.connect(lambda **kw: bump_version(), sender=model, weak=False, dispatch_uid=f"wiki-bump-{model.__name__}")
            post_delete.connect(lambda **kw: bump_version(), sender=model, weak=False, dispatch_uid=f"wiki-bump-del-{model.__name__}")
