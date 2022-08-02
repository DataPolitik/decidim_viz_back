from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('comments/', views.comments, name='comments'),
    path('endorsements/', views.endorsements, name='endorsements'),
    path('languages/', views.get_comment_languages, name='languages'),
    path('languages/count/<lang>', views.get_num_comments_per_language, name='languages'),
    path('endorsements/histogram', views.group_by_endorsements, name='endorsements_histogram'),
    path('comments/histogram', views.group_by_comments, name='comments_histogram')
]