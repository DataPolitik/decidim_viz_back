import pickle
import networkx as nx
from math import sqrt
from os.path import exists
import plotly.graph_objects as go

from django.http import HttpResponse, JsonResponse
from stats.models import Proposal, User


def index(request):
    return HttpResponse("Hello, world. You're at the polls index.")


def make_edge(x, y, text, width):
    return  go.Scatter(x         = x,
                       y         = y,
                       line      = dict(width = width,
                                   color = '#888'),
                       hoverinfo = 'text',
                       text      = ([]),
                       mode      = 'lines')


def prepare_graph(G):
    pos_ = nx.spring_layout(G)
    # For each edge, make an edge_trace, append to list
    edge_trace = []
    for edge in G.edges():
        phi = G.edges()[edge]['phi']
        if phi == 0:
            continue
        char_1 = edge[0]
        char_2 = edge[1]
        x0, y0 = pos_[char_1]
        x1, y1 = pos_[char_2]
        text = "{} -- {} : {}".format(char_1, char_2, phi)

        trace = make_edge([x0, x1, None], [y0, y1, None], text,
                              width=0.5)
        edge_trace.append(trace)

    # Make a node trace
    node_trace = go.Scatter(x=[],
                            y=[],
                            text=[],
                            textposition="top center",
                            textfont_size=10,
                            mode='markers+text',
                            hoverinfo='none',
                            marker=dict(color=[],
                                        size=[],
                                        line=None))
    # For each node in midsummer, get the position and size and add to the node_trace
    for node in G.nodes():
        x, y = pos_[node]
        node_trace['x'] += tuple([x])
        node_trace['y'] += tuple([y])
        node_trace['marker']['color'] += tuple(['cornflowerblue'])

    # Customize layout
    layout = go.Layout(
        xaxis={'showgrid': False, 'zeroline': False},  # no gridlines
        yaxis={'showgrid': False, 'zeroline': False},  # no gridlines
    )  # Create figure
    fig = go.Figure(layout=layout)  # Add all edge traces
    for trace in edge_trace:
        fig.add_trace(trace)  # Add node trace
    fig.add_trace(node_trace)  # Remove legend
    fig.update_layout(showlegend=False)  # Remove tick labels
    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(showticklabels=False)  # Show figure
    fig.write_image("fig1.svg")


def endorsements(request):
    if exists("stats/cache/all.pickle"):
        with open('stats/cache/all.pickle', 'rb') as handle:
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

        with open('stats/cache/all.pickle', 'wb') as handle:
            pickle.dump(response, handle, protocol=pickle.HIGHEST_PROTOCOL)

    return JsonResponse(response)
