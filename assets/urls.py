from django.urls import path

from .views import browse_nextcloud


app_name = "assets"

urlpatterns = [
    path("nextcloud/browse/", browse_nextcloud, name="nextcloud_browse",),
]