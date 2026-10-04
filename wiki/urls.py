from django.urls import path

from . import views

app_name = "wiki"

urlpatterns = [
    path("", views.resolve, name="home"),
    path("search/", views.search, name="search"),
    path("go/<slug:link>/", views.direct, name="direct"),
    path("<path:path>", views.resolve, name="resolve"),
]