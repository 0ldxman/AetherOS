from django.urls import path

from studio import views
from studio.api import api

urlpatterns = [
    path("api/", api.urls),
    path("", views.shell, name="studio"),
]
