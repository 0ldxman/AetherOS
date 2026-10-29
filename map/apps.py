from django.apps import AppConfig


class MapConfig(AppConfig):
    name = 'map'

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from map.cache import bump_version
        from map.models import Country, CountryLabel, Ownership, Province

        for model in (Country, CountryLabel, Ownership, Province):
            post_save.connect(lambda **kw: bump_version(), sender=model, weak=False, dispatch_uid=f"map-bump-{model.__name__}")
            post_delete.connect(lambda **kw: bump_version(), sender=model, weak=False, dispatch_uid=f"map-bump-del-{model.__name__}")
