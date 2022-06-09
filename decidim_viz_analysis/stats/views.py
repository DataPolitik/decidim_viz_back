import itertools
import json

import pandas as pd

from django.http import HttpResponse, JsonResponse
from stats.models import Proposal, User

from stats.phi.phi import __compute_phi


def index(request):
    return HttpResponse("Hello, world. You're at the polls index.")


def endorsements(request):
    threshold = 1
    list_of_proposals = Proposal.objects.values_list('id_proposal', flat=True)[:100]
    list_of_users = User.objects.values_list('id', flat=True)[:100]
    dataframe_proposals = pd.DataFrame(0, columns=list_of_users, index=list_of_proposals, dtype='int16')
    dict_users = dict()
    for user in list_of_users:
        dict_users[user] = dict()

    for proposal in list_of_proposals:
        users = User.objects.filter(supports__id_proposal=proposal)
        for user in users:
            if user.id in list_of_users:
                dataframe_proposals[user.id][proposal] = dataframe_proposals[user.id][proposal] + 1

    for user_couple in set(itertools.combinations(list_of_users, 2)):
        user_a = user_couple[0]
        user_b = user_couple[1]

        proposals_a = dataframe_proposals[user_a]
        proposals_b = dataframe_proposals[user_b]
        phi, t = __compute_phi(proposals_a, proposals_b)
        if abs(t) > threshold:
            dict_users[user_a][user_b] = phi
            dict_users[user_b][user_a] = phi

    return JsonResponse(dict_users)
