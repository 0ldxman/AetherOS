from django.urls import path
from . import views

app_name = 'map'

urlpatterns = [
    path('', views.index, name='index'),
    path("api/province-colors/", views.province_colors, name="province_colors"),
    path("api/country-labels/", views.country_labels, name="country_labels"),
    path("timeline/", views.timeline_dates, name="timeline_dates"),
    path("api/scenes/", views.scene_list, name="scene_list"),
    path("api/scenes/<slug:slug>/", views.scene_detail, name="scene_detail"),
]