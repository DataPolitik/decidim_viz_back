import pickle
from datetime import datetime
from random import random, shuffle, choice

import plotly
import plotly.graph_objects as go

import networkx as nx
import networkx.algorithms.community as nxcom

from math import sqrt
from os.path import exists
from collections import Counter

import numpy as np
from django.db.models import Count
from django.db.models.functions import TruncDay, TruncMonth, TruncYear

from django.http import HttpResponse, JsonResponse, HttpResponseNotFound
from stats.models import Proposal, User, Comment, Category




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


def get_color(i, r_off=1, g_off=1, b_off=1):
    n = 26
    r = (n * (i + r_off) * 3) % 255
    g = (n * (i + r_off) * 5) % 255
    b = (n * (i + r_off) * 7) % 255
    return (r, g, b)


def community_net(G_in):
    G_out = nx.Graph()
    node_color = {}
    node_community = {}
    communities = nxcom.greedy_modularity_communities(G_in)
    for i, com in enumerate(communities):
        for v in com:
            G_out.add_node(v)
            node_color[v] = get_color(i)
            node_community[v] = i
    G_out.add_edges_from(G_in.edges())
    return node_color, node_community, G_out


def filter_nodes(G, minimum_degree= 2):
    remove = [node for node,degree in dict(G.degree()).items() if degree < minimum_degree]
    G.remove_nodes_from(remove)
    return G


def comments(request):
    if exists("stats/cache/comments_all.pickle"):
        with open('stats/cache/comments_all.pickle', 'rb') as handle:
            responseHtml = pickle.load(handle)
    return HttpResponse(responseHtml, content_type="text/html")


def get_comments_node_colors(request):
    with open('stats/cache/comment_node_colors.pickle', 'rb') as file:
        community_dict = pickle.load(file)
        return JsonResponse(community_dict)


def generate_plotly_graph(G, positions, dict_names, node_color):

    edge_x = []
    edge_y = []

    for edge in G.edges():
        x0, y0 = positions[edge[0]]
        x1, y1 = positions[edge[1]]
        edge_x.append(x0)
        edge_x.append(x1)
        edge_x.append(None)
        edge_y.append(y0)
        edge_y.append(y1)
        edge_y.append(None)

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=1.5, color='#888'),
        hoverinfo='none',
        mode='lines')

    node_x = []
    node_y = []
    color = []
    for node in G.nodes():
        x, y = positions[node]
        node_x.append(x)
        node_y.append(y)
        color.append(node_color[node])

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers',
        hoverinfo='text',
        marker=dict(
            showscale=False,
            color=[],
            size=10,
            colorbar=dict(
                title='Number of links',
                xanchor='left',
                titleside='right'
            ),
            line_width=2))

    node_adjacencies = []
    node_text = []
    for node, adjacencies in enumerate(G.adjacency()):
        node_adjacencies.append(len(adjacencies[1]))
        node_text.append(str(node))

    node_trace.marker.color = node_adjacencies
    node_trace.text = node_text

    fig = go.Figure(data=[edge_trace, node_trace],
                    layout=go.Layout(
                        title='',
                        titlefont_size=16,
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=20, l=5, r=5, t=40),
                        annotations=[dict(
                            text="",
                            showarrow=False,
                            xref="paper", yref="paper",
                            x=0.005, y=-0.002)],
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                    )


    return plotly.offline.plot(fig, include_plotlyjs=False, output_type='div')


def compute_phi(x0,x1,y0,y1,n):

    n11 = len(x1.intersection(y1))  # intersection user a and b
    n10 = len(x1.intersection(y0))
    n01 = len(x0.intersection(y1))

    n_1 = n11 + n01
    n1_ = n11 + n10

    den_product = (n1_ * n_1 * (n - n1_) * (n - n_1))
    den_product = den_product if den_product > 0 else 1

    phi = (n * n11 - n1_ * n_1) / sqrt(den_product)
    t = 1 + (phi * sqrt(n - 2)) / 1 + (sqrt(1 - phi * phi))

    return phi,t


def endorsements(request):
    if exists("stats/cache/endorsement_all.pickle"):
        with open('stats/cache/endorsement_all.pickle', 'rb') as handle:
            responseHtml = pickle.load(handle)
    return HttpResponse(responseHtml, content_type="text/html")


def get_endorsement_node_colors(request):
    with open('stats/cache/endorsement_node_colors.pickle', 'rb') as file:
        community_dict = pickle.load(file)
        return JsonResponse(community_dict)


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


def __gini_coefficient(x):
    """Compute Gini coefficient of array of values"""
    diffsum = 0
    x = np.array(x)
    den = len(x)**2 * np.mean(x)

    for i, xi in enumerate(x[:-1], 1):
        diffsum += np.sum(np.abs(xi - x[i:]))

    gini = diffsum / den
    contributions = []
    for i, xi in enumerate(x[:-1], 1):
        sub_total = diffsum - np.sum(np.abs(xi - x[i:]))
        partial_gini = sub_total / den
        contribution = gini - partial_gini
        contributions.append(contribution)
    contributions.append(0)
    return gini, contributions


def get_proposals_by_supports(request, limit):
    proposals = Proposal.objects.order_by('-endorsements')[0:limit]
    response = {'proposals': [], 'gini': -1}

    endorsements_values = []

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
        endorsements_values.append(proposal.endorsements)

    gini_responses = __gini_coefficient(endorsements_values)
    response['gini'] = {'value': gini_responses[0], 'contributions': gini_responses[1]}

    return JsonResponse(response)


def get_users_by_comments(request, limit):
    comments_per_users = Comment.objects.values('author')\
        .annotate(total_comments=Count('author'))\
        .order_by('-total_comments')[0:limit]
    response = {'comments': [], 'gini': -1}
    comments_values = []

    for comment in comments_per_users:
        author_name = User.objects.get(id=comment['author'])
        response['comments'].append(
            {
                'id': comment['author'],
                'name': str(author_name),
                'comments': comment['total_comments'],
            }
        )
        comments_values.append(comment['total_comments'])

    gini_responses = __gini_coefficient(comments_values)
    response['gini'] = {'value': gini_responses[0], 'contributions': gini_responses[1]}

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

    comments_values = []

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
        comments_values.append(proposal.num_comments)

    gini_responses = __gini_coefficient(comments_values)
    response['gini'] = {'value': gini_responses[0], 'contributions': gini_responses[1]}

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
    categories_proposals = []
    for category in categories:
        response['categories'].append(
            {'id':category.pk,
             'name_es': category.name_es,
             'name_ca': category.name_ca,
             'name_en': category.name_en,
             'categories': category.num_proposals
            }
        )
        categories_proposals.append(category.num_proposals)
    gini_responses = __gini_coefficient(categories_proposals)
    response['gini'] = {'value': gini_responses[0], 'contributions': gini_responses[1]}
    return JsonResponse(response)


def get_temporal_limits(request):
    proposals = Proposal.objects.all().order_by('published_at')
    comments = Comment.objects.all().order_by('created_at')

    first_proposal = proposals[0]
    last_proposal = proposals.reverse()[0]

    first_comment = comments[0]
    last_comment = comments.reverse()[0]


    response = {
        'proposals_from': first_proposal.published_at,
        'proposals_to': last_proposal.published_at,
        'comments_from': first_comment.created_at,
        'comments_to': last_comment.created_at
    }
    return JsonResponse(response)


def get_categories_by_comments(request):
    proposals = Proposal.objects.all().annotate(num_comments=Count('comment'))
    categories = {}
    categories_comments = []
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
        categories_comments.append(category_count)
    response['categories'] = sorted(response['categories'], key=lambda d: d['comments'], reverse=True)
    gini_responses = __gini_coefficient(categories_comments)
    response['gini'] = {'value': gini_responses[0], 'contributions': gini_responses[1]}
    return JsonResponse(response)


def get_num_comments_per_language(request):
    language_list = _list_of_languages()
    response = {'languages': []}
    for lang in language_list:
        response['languages'].append({'language': lang, 'count': Comment.objects.filter(language=lang).count()})
    response['languages'] = sorted(response['languages'], key=lambda d: d['count'], reverse=True)

    return JsonResponse(response)


def get_most_commented_proposal(request):
    proposal = Proposal.objects.all().annotate(num_comments=Count('comment')).order_by("num_comments")[0]
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
    proposal = Proposal.objects.all().annotate(num_endorses=Count('users')).order_by("num_endorses")[0]
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


def comments_per_user(request):
    comments = Comment.objects.values('author').annotate(total_per_author=Count('author')).order_by()

    for comment in comments:
        print(comment)


def download_data(request):
    try:
        with open("stats/data/futureu.europa.eu-open-data.zip", 'rb') as f:
            file_data = f.read()
        # sending response
        response = HttpResponse(file_data, content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="futureu.europa.eu-open-data.zip"'

    except IOError:
        # handle file not exist case here
        response = HttpResponseNotFound('<h1>File not exist</h1>')
    return response


