from django.urls import path

from .views import asset_file


app_name = "public_assets"

urlpatterns = [
    path(
        "<int:asset_id>/",
        asset_file,
        name="asset_file",
    ),
]