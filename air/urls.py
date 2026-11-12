from django.urls import path

from air import views

app_name = "air"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/tune/", views.tune, name="tune"),
    path("api/listen/", views.listen, name="listen"),
    path("api/tx/", views.transmit, name="tx"),
    path("api/scan/", views.scan, name="scan"),
    path("api/key/", views.cipher_key, name="key"),
    path("api/callsign/", views.callsign, name="callsign"),
    path("api/report/", views.report, name="report"),
]
