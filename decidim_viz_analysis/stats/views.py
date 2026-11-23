from datetime import datetime
from collections import Counter
from django.db.models import Count
from django.db.models.functions import TruncDay, TruncMonth, TruncYear

from django.http import HttpResponse, JsonResponse
from stats import statistics
from stats.models import Proposal, User, Comment, Category
from stats.networks import community_colors, get_network




def index(request):
    return HttpResponse("Hello, world. You're at the polls index.")


def parse_proposal(proposal):
    return {
                'id': proposal.id_proposal,
                'title_es': proposal.proposal_title_es,
                'title_fr': proposal.proposal_title_fr,
                'title_en': proposal.proposal_title_en,
                'url': proposal.url,
                'latitude': proposal.latitude,
                'longitude': proposal.longitude
            }


def comments(request):
    """phi network of users who comment on the same proposals."""
    return JsonResponse(get_network('comments'))


def endorsements(request):
    """phi network of users who endorse the same proposals."""
    return JsonResponse(get_network('endorsements'))


def comments_modularity(request):
    """Modularity of the community partition of the comments network."""
    return JsonResponse({'modularity': get_network('comments')['modularity']})


def endorsements_modularity(request):
    """Modularity of the community partition of the endorsements network."""
    return JsonResponse({'modularity': get_network('endorsements')['modularity']})


def _community_colors(request, kind):
    try:
        n_proposals = int(request.GET.get('proposals', 3))
    except ValueError:
        return JsonResponse({'error': 'proposals must be an integer'}, status=400)
    if n_proposals < 0:
        return JsonResponse({'error': 'proposals must be >= 0'}, status=400)
    return JsonResponse(community_colors(kind, n_proposals, request.GET.get('lang', 'en')))


def comments_colors(request):
    """Communities of the comments network keyed by colour, with their top proposals.

    Query parameters: proposals (per community, default 3), lang (en, es or fr; default en).
    """
    return _community_colors(request, 'comments')


def endorsements_colors(request):
    """Communities of the endorsements network keyed by colour, with their top proposals.

    Query parameters: proposals (per community, default 3), lang (en, es or fr; default en).
    """
    return _community_colors(request, 'endorsements')


def group_by_endorsements(request):
    response = Proposal.objects.values('id_proposal',).annotate(total=Count('users'),)
    total_list = [e['total'] for e in response]
    counts = dict(Counter(total_list))
    list_response = []
    for key, value in counts.items():
        list_response.append({'comments': key, 'count': value})
    list_response = sorted(list_response, key=lambda d: d['comments'])
    return JsonResponse({'histogram': list_response})


def group_by_comments(request):
    response = Proposal.objects.values('id_proposal',).annotate(total=Count('comments'),)
    total_list = [e['total'] for e in response]
    counts = dict(Counter(total_list))
    list_response = []
    for key, value in counts.items():
        list_response.append({'comments': key, 'count': value})
    list_response = sorted(list_response, key=lambda d: d['comments'])
    return JsonResponse({'histogram': list_response})


def _list_of_languages():
    response = Comment.objects.values('language') # Distinct is not supported on sqlite
    return list(set([l['language'] for l in response]))


def get_comment_languages(request):
    language_list = _list_of_languages()
    return JsonResponse(language_list, safe=False)


def get_proposals_by_supports(request, limit):
    proposals = Proposal.objects.order_by('-endorsements')[0:limit]
    response = {'proposals': []}

    for proposal in proposals:
        response['proposals'].append(
            {
                'id': proposal.id_proposal,
                'title_es': proposal.proposal_title_es,
                'title_fr': proposal.proposal_title_fr,
                'title_en': proposal.proposal_title_en,
                'endorsements': proposal.endorsements,
                'category': proposal.category.pk if proposal.category is not None else ''
            }
        )
    response['gini'] = statistics.gini_for(dict(Proposal.objects.values_list('id_proposal', 'endorsements')),
                                           [p['id'] for p in response['proposals']])
    return JsonResponse(response)


def get_proposal(request, id_proposal):
    if Proposal.objects.filter(id_proposal=id_proposal).exists():
        proposal = Proposal.objects.get(id_proposal=id_proposal)
        return JsonResponse(parse_proposal(proposal))
    else:
        return JsonResponse({}, status=404)


def get_proposals_by_comments(request, limit):
    proposals = Proposal.objects.annotate(num_comments=Count('comment')).order_by('-num_comments')[0:limit]
    response = {'proposals': []}

    for proposal in proposals:
        response['proposals'].append(
            {
                'id': proposal.id_proposal,
                'title_es': proposal.proposal_title_es,
                'title_fr': proposal.proposal_title_fr,
                'title_en': proposal.proposal_title_en,
                'endorsements': proposal.endorsements,
                'category': proposal.category.pk if proposal.category is not None else '',
                'comments': proposal.num_comments
            }
        )
    comment_counts = dict(Proposal.objects.annotate(n=Count('comment')).values_list('id_proposal', 'n'))
    response['gini'] = statistics.gini_for(comment_counts, [p['id'] for p in response['proposals']])
    return JsonResponse(response)


def get_categories(request):
    categories = Category.objects.all()
    response = {'categories': []}
    for category in categories:
        response['categories'].append(
            {'id':category.pk,
             'name_es': category.name_es,
             'name_ca': category.name_ca,
             'name_en': category.name_en,
            }
        )
    return JsonResponse(response)


def get_categories_by_proposals(request, limit):
    categories = Category.objects.annotate(num_proposals=Count('proposal')).order_by('-num_proposals')[0:limit]
    response = {'categories': []}
    for category in categories:
        response['categories'].append(
            {'id':category.pk,
             'name_es': category.name_es,
             'name_ca': category.name_ca,
             'name_en': category.name_en,
             'categories': category.num_proposals
            }
        )
    proposal_counts = dict(Category.objects.annotate(n=Count('proposal')).values_list('id', 'n'))
    response['gini'] = statistics.gini_for(proposal_counts, [c['id'] for c in response['categories']])
    return JsonResponse(response)


def get_categories_by_comments(request):
    proposals = Proposal.objects.all().annotate(num_comments=Count('comment'))
    categories = {}
    for proposal in proposals:
        if proposal.category is not None:
            if proposal.category.pk in categories:
                categories[proposal.category.pk] = categories[proposal.category.pk] + proposal.num_comments
            else:
                categories[proposal.category.pk] = proposal.num_comments

    response = {'categories': []}
    for category_id, category_count in categories.items():
        category_detail = Category.objects.get(pk=category_id)
        response['categories'].append(
            {'id': category_id,
             'name_es': category_detail.name_es,
             'name_ca': category_detail.name_ca,
             'name_en': category_detail.name_en,
             'comments': category_count
            }
        )
    response['categories'] = sorted(response['categories'], key=lambda d: d['comments'], reverse=True)
    all_categories = {category_id: categories.get(category_id, 0)
                      for category_id in Category.objects.values_list('id', flat=True)}
    response['gini'] = statistics.gini_for(all_categories, [c['id'] for c in response['categories']])
    return JsonResponse(response)


# Endpoints used by the Statistics and Activity pages; see stats/statistics.py.

def get_temporal_limits(request):
    return JsonResponse(statistics.temporal_limits())


def get_participation_types(request):
    return JsonResponse(statistics.participation_types())


def get_users_by_comments(request, limit):
    return JsonResponse(statistics.top_commenters(limit))


def get_comments_length(request):
    return JsonResponse({'box_data': statistics.comment_lengths()})


def get_comments_depth(request):
    return JsonResponse({'box_data': statistics.comment_depths()})


def get_comments_per_user(request):
    return JsonResponse({'box_data': list(statistics.comments_per_user().values())})


def get_proposals_comments_count(request):
    return JsonResponse(statistics.proposals_with_and_without_comments())


def get_hours_to_first_comment(request):
    return JsonResponse({'box_data': statistics.hours_to_first_comment()})


def get_num_comments_per_language(request):
    language_list = _list_of_languages()
    response = {'languages': []}
    for lang in language_list:
        response['languages'].append({'language': lang, 'count': Comment.objects.filter(language=lang).count()})
    response['languages'] = sorted(response['languages'], key=lambda d: d['count'], reverse=True)

    return JsonResponse(response)


def get_most_commented_proposal(request):
    proposal = Proposal.objects.annotate(num_comments=Count('comment')).order_by('-num_comments', 'id_proposal').first()
    if proposal is None:
        return JsonResponse({}, status=404)
    response = {
        'id': proposal.id_proposal,
        'title_es': proposal.proposal_title_es,
        'title_fr': proposal.proposal_title_fr,
        'title_en': proposal.proposal_title_en,
        'endorsements': proposal.endorsements,
        'category': proposal.category.pk if proposal.category is not None else '',
        'comments': proposal.num_comments
    }
    return JsonResponse(response)


def get_most_endorsed_proposal(request):
    proposal = Proposal.objects.annotate(num_endorses=Count('users')).order_by('-num_endorses', 'id_proposal').first()
    if proposal is None:
        return JsonResponse({}, status=404)
    response = {
        'id': proposal.id_proposal,
        'title_es': proposal.proposal_title_es,
        'title_fr': proposal.proposal_title_fr,
        'title_en': proposal.proposal_title_en,
        'endorsements': proposal.endorsements,
        'category': proposal.category.pk if proposal.category is not None else '',
    }
    return JsonResponse(response)


def get_daily_proposal_histogram(request, date_from, date_to):
    datetime_from = datetime.strptime(date_from, '%Y-%m-%d')
    datetime_to = datetime.strptime(date_to, '%Y-%m-%d')

    proposals = Proposal.objects.filter(published_at__gt=datetime_from, published_at__lte=datetime_to).annotate(
        date_truncated=TruncDay('published_at')
    ).values('date_truncated').annotate(count=Count('date_truncated')).order_by('-date_truncated')

    response = {
        'history': [],
        'count': len(proposals),
        'name': 'proposals'
                }

    for proposal in proposals:
        response['history'].append(
            {
                'key': proposal['date_truncated'].strftime("%d/%m/%Y"),
                'value': proposal['count']
            }
        )
    return JsonResponse(response)


def get_proposals_by_date(request, date_from, date_to):
    datetime_from = datetime.strptime(date_from, '%Y-%m-%d')
    datetime_to = datetime.strptime(date_to, '%Y-%m-%d')

    proposals = Proposal.objects.filter(published_at__gt=datetime_from, published_at__lte=datetime_to)

    response_list = []

    for proposal in proposals:
        response_list.append(
            {
                'id': proposal.id_proposal,
                'title_es': proposal.proposal_title_es,
                'title_fr': proposal.proposal_title_fr,
                'title_en': proposal.proposal_title_en,
                'url': proposal.url,
                'latitude': proposal.latitude,
                'longitude': proposal.longitude,
                'endorsements': proposal.endorsements,
                'category': proposal.category.pk if proposal.category is not None else '',
            }
        )
    return JsonResponse(response_list, safe=False)


def get_cumulative_proposal_histogram(request, date_from, date_to):
    datetime_from = datetime.strptime(date_from, '%Y-%m-%d')
    datetime_to = datetime.strptime(date_to, '%Y-%m-%d')

    proposals = Proposal.objects.filter(published_at__lte=datetime_to).annotate(
        date_truncated=TruncDay('published_at')
    ).values('date_truncated').annotate(count=Count('date_truncated')).order_by('date_truncated')

    response = {
        'history': [],
        'count': len(proposals),
        'name': 'proposals'
                }

    sum = 0
    for proposal in proposals:
        sum = sum + proposal['count']
        if proposal['date_truncated'].timestamp() >= datetime_from.timestamp():
            response['history'].append(
                {
                    'key': proposal['date_truncated'].strftime("%d/%m/%Y"),
                    'value': sum
                }
            )
    response['history'].reverse()
    return JsonResponse(response)


def get_daily_comments_histogram_per_proposal(request, id_proposal):

    comments = Comment.objects.filter(proposal_replied__id_proposal=id_proposal).annotate(
        date_truncated=TruncDay('created_at')
    ).values('date_truncated').annotate(count=Count('date_truncated')).order_by('-date_truncated')

    response = {
        'history': [],
        'count': len(comments),
        'name': 'proposals'
                }

    for comment in comments:
        response['history'].append(
            {
                'key': comment['date_truncated'].strftime("%d/%m/%Y"),
                'value': comment['count']
            }
        )
    return JsonResponse(response)


def get_users_proposal(request, id_proposal):

    users = User.objects.filter(comment__proposal_replied__id_proposal=id_proposal).annotate(count=Count('id')).order_by('-count')

    response = {
        'history': [],
        'count': len(users),
        'name': 'users_by_proposal'
    }

    for user in users:
        response['history'].append(
            {
                'id': user.id,
                'name': user.name,
                'count': user.count
            }
        )
    return JsonResponse(response)


def get_daily_comments_histogram(request, date_from, date_to):
    datetime_from = datetime.strptime(date_from, '%Y-%m-%d')
    datetime_to = datetime.strptime(date_to, '%Y-%m-%d')

    comments = Comment.objects.filter(created_at__gt=datetime_from, created_at__lte=datetime_to).annotate(
        date_truncated=TruncDay('created_at')
    ).values('date_truncated').annotate(count=Count('date_truncated')).order_by('-date_truncated')

    response = {
        'history': [],
        'count': len(comments),
        'name': 'proposals'
                }

    for comment in comments:
        response['history'].append(
            {
                'key': comment['date_truncated'].strftime("%d/%m/%Y"),
                'value': comment['count']
            }
        )
    return JsonResponse(response)


def get_cumulative_comment_histogram(request, date_from, date_to):
    datetime_from = datetime.strptime(date_from, '%Y-%m-%d')
    datetime_to = datetime.strptime(date_to, '%Y-%m-%d')

    comments = Comment.objects.filter(created_at__lte=datetime_to).annotate(
        date_truncated=TruncDay('created_at')
    ).values('date_truncated').annotate(count=Count('date_truncated')).order_by('date_truncated')

    response = {
        'history': [],
        'count': len(comments),
        'name': 'comments'
                }

    sum = 0
    for comment in comments:
        sum = sum + comment['count']
        if comment['date_truncated'].timestamp() >= datetime_from.timestamp():
            response['history'].append(
                {
                    'key': comment['date_truncated'].strftime("%d/%m/%Y"),
                    'value': sum
                }
            )
    response['history'].reverse()
    return JsonResponse(response)

