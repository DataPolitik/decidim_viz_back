import pickle
import random

import networkx as nx
import networkx.algorithms.community as nxcom

from math import sqrt
from os.path import exists
from collections import Counter
from django.db.models import Count

from django.http import HttpResponse, JsonResponse
from stats.models import Proposal, User, Comment, Category




def index(request):
    return HttpResponse("Hello, world. You're at the polls index.")


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
            response = pickle.load(handle)
    else:
        threshold = 0.5
        set_of_proposals = set(Proposal.objects.values_list('id_proposal', flat=True)[:200])
        list_of_users = User.objects.all()[:200]
        G = nx.Graph()
        dict_users = dict()
        cache_proposals = dict()
        dict_names = dict()

        for user in list_of_users:
            dict_users[user.id] = dict()
            dict_names[user.id] = user.name
            cache_proposals[user.id] = set(Comment.objects.filter(author=user.id).values_list('proposal_replied_id', flat=True))
            G.add_node(user.id)

        n = len(set_of_proposals)

        count_relations = 0
        for user_a in list_of_users:
            x1 = cache_proposals[user_a.id]
            for user_b in list_of_users:
                if user_a == user_b:
                    continue

                y1 = cache_proposals[user_b.id]

                x0 = set_of_proposals.difference(x1)
                y0 = set_of_proposals.difference(y1)

                n11 = len(x1.intersection(y1))
                n10 = len(x1.intersection(y0))
                n01 = len(x0.intersection(y1))

                n_1 = n11 + n01
                n1_ = n11 + n10

                den_product = (n1_ * n_1 * (n - n1_)*(n-n_1))
                den_product = den_product if den_product > 0 else 1

                phi = (n * n11 - n1_*n_1) / sqrt(den_product)

                t = 1 + (phi * sqrt(n-2)) / 1 + (sqrt(1 - phi * phi))

                if t > threshold or t < threshold:
                    count_relations = count_relations + 1
                    dict_users[user_a.id][user_b.id] = phi
                    dict_users[user_b.id][user_a.id] = phi

                    G.add_edge(user_a.id, user_b.id)
                    G[user_a.id][user_b.id]['phi'] = phi


        node_color, node_community, G = community_net(G)
        pos_ = nx.circular_layout(G)
        response = {'users': dict_users,
                    'positions': dict(),
                    'usernames': dict_names,
                    'colors': node_color
                    }

        for key, coordinates in pos_.items():
            response['positions'][key] = list(coordinates)

        with open('stats/cache/comments_all.pickle', 'wb') as handle:
            pickle.dump(response, handle, protocol=pickle.HIGHEST_PROTOCOL)

    return JsonResponse(response)


def endorsements(request):
    if exists("stats/cache/endorsement_all.pickle"):
        with open('stats/cache/endorsement_all.pickle', 'rb') as handle:
            response = pickle.load(handle)
    else:
        threshold = 0.5
        set_of_proposals = set(Proposal.objects.values_list('id_proposal', flat=True)[:200])
        list_of_users = User.objects.all()[:200]
        G = nx.Graph()
        dict_users = dict()
        cache_proposals = dict()
        dict_names = dict()
        for user in list_of_users:
            dict_users[user.id] = dict()
            dict_names[user.id] = user.name
            cache_proposals[user.id] = set(user.proposal_set.values_list('id_proposal', flat=True))
            G.add_node(user.id)

        n = len(set_of_proposals)

        count_relations = 0
        for user_a in list_of_users:
            x1 = cache_proposals[user_a.id]
            for user_b in list_of_users:
                if user_a == user_b:
                    continue

                y1 = cache_proposals[user_b.id]

                x0 = set_of_proposals.difference(x1)
                y0 = set_of_proposals.difference(y1)

                n11 = len(x1.intersection(y1))
                n10 = len(x1.intersection(y0))
                n01 = len(x0.intersection(y1))

                n_1 = n11 + n01
                n1_ = n11 + n10

                den_product = (n1_ * n_1 * (n - n1_)*(n-n_1))
                den_product = den_product if den_product > 0 else 1

                phi = (n * n11 - n1_*n_1) / sqrt(den_product)

                t = 1 + (phi * sqrt(n-2)) / 1 + (sqrt(1 - phi * phi))

                if t > threshold or t < threshold:
                    count_relations = count_relations + 1
                    dict_users[user_a.id][user_b.id] = phi
                    dict_users[user_b.id][user_a.id] = phi

                    G.add_edge(user_a.id, user_b.id)
                    G[user_a.id][user_b.id]['phi'] = phi

        node_color, node_community, G = community_net(G)
        pos_ = nx.circular_layout(G)
        response = {'users': dict_users,
                    'positions': dict(),
                    'usernames': dict_names,
                    'colors': node_color
                    }

        for key, coordinates in pos_.items():
            response['positions'][key] = list(coordinates)

        with open('stats/cache/endorsement_all.pickle', 'wb') as handle:
            pickle.dump(response, handle, protocol=pickle.HIGHEST_PROTOCOL)

    return JsonResponse(response)


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
    return JsonResponse(response)


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


def getProposalHistogram(request, date_from, date_to):
    proposals = Proposal.objects.values('published_at').annotate(c=Count('id_proposal'))
    print(proposals)