from django.urls import path

from assets.views import asset_content, asset_viewer


app_name = "asset_viewer"

urlpatterns = [
    path(
        "<uuid:public_id>/",
        asset_viewer,
        name="viewer",
    ),
    path(
        "<uuid:public_id>/content/",
        asset_content,
        name="content",
    ),
]