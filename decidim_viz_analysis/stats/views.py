import pickle
import networkx as nx
from math import sqrt
from os.path import exists
from collections import Counter
from django.db.models import Count

from django.http import HttpResponse, JsonResponse
from django_pivot.pivot import pivot
from stats.models import Proposal, User, Comment


def index(request):
    return HttpResponse("Hello, world. You're at the polls index.")


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

        pos_ = nx.circular_layout(G)
        response = {'users': dict_users,
                    'positions': dict(),
                    'usernames': dict_names
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

        pos_ = nx.circular_layout(G)
        response = {'users': dict_users,
                    'positions': dict(),
                    'usernames': dict_names
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
        list_response.append({'count': key, 'size': value})
    list_response = sorted(list_response, key=lambda d: d['count'])
    return JsonResponse({'histogram': list_response})


def group_by_comments(request):
    response = Proposal.objects.values('id_proposal',).annotate(total=Count('comments'),)
    total_list = [e['total'] for e in response]
    counts = Counter(total_list)
    list_response = []
    for key, value in counts.items():
        list_response.append({'count': key, 'size': value})
    list_response = sorted(list_response, key=lambda d: d['count'])
    return JsonResponse({'histogram': list_response})
