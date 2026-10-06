from django.urls import path
from . import views

app_name = 'map'

urlpatterns = [
    path('', views.index, name='index'),
    path("api/province-colors/", views.province_colors, name="province_colors"),
    path("api/country-labels/", views.country_labels, name="country_labels"),
]