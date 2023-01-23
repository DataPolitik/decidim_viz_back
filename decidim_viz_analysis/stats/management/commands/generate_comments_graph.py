from django.core.management.base import BaseCommand
from mycolorpy import colorlist as mcp


import pickle
import plotly
import plotly.graph_objects as go
import networkx.algorithms.community as nxcom
import networkx as nx

from collections import Counter
from math import sqrt
from collections import defaultdict
from stats.models import Proposal, User, Comment


COLORS = mcp.gen_color(cmap="tab20", n=50)


def compute_phi(x0,x1,y0,y1,n):

    n11 = len(x1.intersection(y1))  # intersection user a and b
    n10 = len(x1.intersection(y0))
    n01 = len(x0.intersection(y1))

    n_1 = n11 + n01
    n1_ = n11 + n10

    den_product = (n1_ * n_1 * (n - n1_) * (n - n_1))
    den_product = den_product if den_product > 0 else 1

    phi = (n * n11 - n1_ * n_1) / sqrt(den_product)
    t = 1 + (phi * sqrt(n  - 2)) / 1 + (sqrt(1 - phi * phi))

    return phi,t


def community_net(G_in):
    G_out = nx.Graph()
    node_color = {}
    node_community = {}
    communities = nxcom.greedy_modularity_communities(G_in)
    modularity_values = nxcom.modularity(G_in, communities)
    for i, com in enumerate(communities):
        community_color = COLORS[i]
        for v in com:
            G_out.add_node(v)
            node_color[v] = community_color
            node_community[v] = i
    G_out.add_edges_from(G_in.edges())
    return node_color, node_community, G_out, modularity_values


def generate_plotly_graph(G, positions, node_color):

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
            color=color,
            size=12,
            colorbar=dict(
                title='Number of links',
                xanchor='left',
                titleside='right'
            ),
            line_width=1))

    node_adjacencies = []
    node_text = []
    for node, adjacencies in enumerate(G.adjacency()):
        node_adjacencies.append(len(adjacencies[1]))
        node_text.append(str(node))


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


def get_proposal_title(id):
    proposal = Proposal.objects.get(id_proposal=id)
    if len(proposal.proposal_title_en) > 0:
        return proposal.proposal_title_en
    elif len(proposal.proposal_title_es) > 0:
        return proposal.proposal_title_es
    else:
        return ""


class Command(BaseCommand):
    help = 'Generates an comments graph'

    def add_arguments(self, parser):
        parser.add_argument('proposal_limit', type=int)
        parser.add_argument('user_limit', type=int)
        parser.add_argument('threshold', type=float)

    def handle(self, *args, **options):
        threshold = options['threshold']
        proposal_limit = options['proposal_limit']
        user_limit = options['user_limit']

        set_of_proposals = set(Proposal.objects.values_list('id_proposal', flat=True)[:proposal_limit])
        list_of_users = User.objects.all()[:user_limit]
        G = nx.DiGraph()
        dict_users = dict()
        cache_proposals = dict()
        dict_names = dict()
        for user in list_of_users:
            dict_users[user.id] = dict()
            dict_names[user.id] = user.name
            cache_proposals[user.id] = set(
                Comment.objects.filter(author=user.id).values_list('proposal_replied_id', flat=True))

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

                phi, t = compute_phi(x0, x1, y0, y1, n)

                if t > threshold:
                    count_relations = count_relations + 1
                    dict_users[user_a.id][user_b.id] = phi
                    dict_users[user_b.id][user_a.id] = phi

                    if phi > 0:
                        G.add_node(user_a.id)
                        G.add_node(user_b.id)
                        G.add_edge(user_a.id, user_b.id)
                        G[user_a.id][user_b.id]['phi'] = phi
        G.remove_nodes_from(list(nx.isolates(G)))
        outdeg = G.out_degree()
        list_to_remove = [n[0] for n in outdeg if n[1] <= 1]

        G.remove_nodes_from(list_to_remove)
        node_color, node_community, G, modularity_value = community_net(G)
        pos_ = nx.circular_layout(G)
        responseHtml = generate_plotly_graph(G, pos_, node_color)
        nx.write_gexf(G, 'stats/cache/comments.gexf')

        script_header = '<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>'
        responseHtml = script_header + responseHtml
        with open('stats/cache/comments_all.pickle', 'wb') as handle:
            pickle.dump(responseHtml, handle, protocol=pickle.HIGHEST_PROTOCOL)
        with open("stats/cache/comment_html.html", "w") as file:
            file.write(responseHtml)
        with open('stats/cache/comment_all_modularity.pickle', 'wb') as handle:
            pickle.dump(modularity_value, handle, protocol=pickle.HIGHEST_PROTOCOL)

        community_dict = dict()
        community_dict['colors'] = dict()
        community_dict['colors']['users'] = defaultdict(list)
        community_dict['colors']['proposals'] = dict()
        community_proposals_dict = defaultdict(list)

        total_users = 0
        for user, color in node_color.items():
            color_hex = color
            community_dict['colors']['users'][color_hex].append(user)
            proposals_by_user = cache_proposals[user]
            community_proposals_dict[color_hex].extend(proposals_by_user)
            total_users = total_users + 1
        community_dict['total'] = total_users

        for color, proposals in community_proposals_dict.items():
            proposals_titles = [get_proposal_title(x) for x in proposals]
            counter = Counter(proposals_titles)
            proposals_most_supported = dict(sorted(counter.items(), key=lambda item: item[1], reverse=True))
            community_dict['colors']['proposals'][color] = proposals_most_supported

        with open("stats/cache/comment_node_colors.pickle", "wb") as file:
            pickle.dump(community_dict, file)
