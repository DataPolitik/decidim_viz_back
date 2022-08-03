from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('comments/', views.comments, name='comments'),
    path('endorsements/', views.endorsements, name='endorsements'),
    path('proposals/supports/<int:limit>', views.get_proposals_by_supports, name='proposals_by_supports'),
    path('proposals/comments/<int:limit>', views.get_proposals_by_comments, name='proposals_by_comments'),
    path('categories/', views.get_categories, name='categories'),
    path('categories/proposals/<int:limit>', views.get_categories_by_proposals, name='categories_by_proposals'),
    path('categories/comments/', views.get_categories_by_comments, name='categories_by_comments'),
    path('languages/', views.get_comment_languages, name='languages'),
    path('languages/count/', views.get_num_comments_per_language, name='languages_count'),
    path('endorsements/histogram', views.group_by_endorsements, name='endorsements_histogram'),
    path('comments/histogram', views.group_by_comments, name='comments_histogram')
]