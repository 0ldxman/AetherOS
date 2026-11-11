from django.urls import path

from guide import views as guide_views
from studio import views
from studio.api import api

urlpatterns = [
    path("api/", api.urls),
    path("guide/media/<str:name>", guide_views.media, name="studio_guide_media"),
    path("preview/page/<str:kind>/", views.preview_page, name="studio_preview_page"),
    path("preview/<str:code>/", views.style_preview, name="studio_style_preview"),
    path("", views.shell, name="studio"),
]
