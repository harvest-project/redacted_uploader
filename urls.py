from django.urls import path

from . import views

urlpatterns = [
    path('transcode', views.TranscodeTorrent.as_view()),
]
