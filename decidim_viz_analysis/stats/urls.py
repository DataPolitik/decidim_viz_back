from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('endorsements/', views.endorsements, name='endorsements'),
]