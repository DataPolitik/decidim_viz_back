from django.urls import path

from . import views
urlpatterns = [
    path('', views.index, name='index'),
    path('comments/', views.comments, name='comments'),
    path('comments/colors', views.get_comments_node_colors, name='comments_colors'),
    path('endorsements/', views.endorsements, name='endorsements'),
    path('endorsements/colors', views.get_endorsement_node_colors, name='endorsements_colors'),
    path('users/by_proposal/<str:id_proposal>/', views.get_users_proposal, name='users_by_proposal'),
    path('users/by_comments/<int:limit>', views.get_users_by_comments, name='users_by_comments'),
    path('proposals/supports/<int:limit>', views.get_proposals_by_supports, name='proposals_by_supports'),
    path('proposal/<int:id_proposal>', views.get_proposal, name='proposal'),
    path('proposals/comments/<int:limit>', views.get_proposals_by_comments, name='proposals_by_comments'),
    path('proposals/endorses/first', views.get_most_endorsed_proposal, name='top_endorsed_proposal'),
    path('proposals/comments/first', views.get_most_commented_proposal, name='top_commented_proposal'),
    path('proposals/by_date/daily/<str:date_from>/<str:date_to>/', views.get_daily_proposal_histogram, name='proposals by date_daily'),
    path('proposals/by_date/<str:date_from>/<str:date_to>/', views.get_proposals_by_date, name='proposals by date'),
    path('proposals/by_date/cumulative/<str:date_from>/<str:date_to>/', views.get_cumulative_proposal_histogram, name='proposals by date_accumulated'),
    path('comments/length', views.get_length_of_comments, name='get_length_of_comments'),
    path('comments/depth', views.get_depth_of_comments, name='get_depth_of_comments'),
    path('comments/by_proposal/<str:id_proposal>/daily/', views.get_daily_comments_histogram_per_proposal, name='comments by proposal'),
    path('comments/by_date/daily/<str:date_from>/<str:date_to>/', views.get_daily_comments_histogram, name='comments by date_daily'),
    path('comments/by_date/cumulative/<str:date_from>/<str:date_to>/', views.get_cumulative_comment_histogram, name='comments by date_accumulated'),
    path('categories/', views.get_categories, name='categories'),
    path('categories/proposals/<int:limit>', views.get_categories_by_proposals, name='categories_by_proposals'),
    path('categories/comments/', views.get_categories_by_comments, name='categories_by_comments'),
    path('languages/', views.get_comment_languages, name='languages'),
    path('languages/count/', views.get_num_comments_per_language, name='languages_count'),
    path('endorsements/histogram', views.group_by_endorsements, name='endorsements_histogram'),
    path('dates/', views.get_temporal_limits, name='dates'),
    path('comments/histogram', views.group_by_comments, name='comments_histogram'),
    path('data/', views.download_data, name='data')
]

