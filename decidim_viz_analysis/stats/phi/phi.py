"""User-user co-participation networks: hypergeometric test, phi weights.

Each user is described by the set of proposals they took part in (commented
on, or endorsed). For two users A and B, with n proposals in total:

    n11 = proposals both took part in
    a   = proposals A took part in,  b = proposals B took part in

Under the null hypothesis that B's b proposals are a random draw from the n,
independent of A, the overlap X follows a hypergeometric distribution
Hypergeom(n, a, b). The one-sided p-value of the observed overlap is

    p = P(X >= n11)

(the same as a one-sided Fisher exact test on the 2x2 table). An edge A-B is
kept when p is significant after correcting for the number of pairs tested,
and it is weighted by the phi coefficient

    phi = (n * n11 - a * b) / sqrt(a * b * (n - a) * (n - b))

Unlike the large-sample t-test on phi, this is exact for the small counts
typical of participation data: two users who touched only the same single
proposal get p = 1/n, which does not survive the multiple-testing correction.

Multiple testing: every unordered pair of active users is a test, so
m = U * (U - 1) / 2. Pairs that share no proposal have p = 1 and are never
significant, so only the pairs with n11 > 0 (the non-zero entries of B @ B.T,
with B the sparse user x proposal incidence matrix) need to be evaluated; the
others still count in m.
"""
import colorsys
from collections import defaultdict
from math import cos, pi, sin

import networkx as nx
import numpy as np
from scipy import sparse
from scipy.stats import hypergeom

DEFAULT_ALPHA = 0.05
DEFAULT_CORRECTION = 'fdr'
CORRECTIONS = ('fdr', 'bonferroni', 'none')
DEFAULT_SEED = 42


def phi_coefficient(n11, a, b, n):
    """Vectorised phi coefficient. Entries with an undefined phi (a or b equal to 0 or n) are NaN."""
    n11, a, b = (np.asarray(x, dtype=float) for x in (n11, a, b))
    den = np.sqrt(a * b * (n - a) * (n - b))
    with np.errstate(divide='ignore', invalid='ignore'):
        phi = np.where(den > 0, (n * n11 - a * b) / den, np.nan)
    return np.clip(phi, -1.0, 1.0)


def overlap_pvalue(n11, a, b, n):
    """One-sided hypergeometric p-value P(X >= n11), X ~ Hypergeom(n, a, b)."""
    n11, a, b = (np.asarray(x, dtype=np.int64) for x in (n11, a, b))
    return hypergeom.sf(n11 - 1, n, a, b)


def significant(pvalues, n_tests, alpha=DEFAULT_ALPHA, correction=DEFAULT_CORRECTION):
    """Boolean mask of the significant p-values.

    n_tests is the total number of hypotheses (m), which can be larger than
    len(pvalues) when the untested ones are known to have p = 1.
    """
    pvalues = np.asarray(pvalues, dtype=float)
    if correction == 'none':
        return pvalues <= alpha
    if correction == 'bonferroni':
        return pvalues <= alpha / n_tests
    if correction == 'fdr':  # Benjamini-Hochberg
        order = np.argsort(pvalues, kind='stable')
        thresholds = alpha * np.arange(1, len(pvalues) + 1) / n_tests
        passed = np.nonzero(pvalues[order] <= thresholds)[0]
        mask = np.zeros(len(pvalues), dtype=bool)
        if len(passed):
            mask[order[:passed[-1] + 1]] = True
        return mask
    raise ValueError('correction must be one of {}'.format(CORRECTIONS))


def phi_edges(memberships, n_proposals, alpha=DEFAULT_ALPHA, correction=DEFAULT_CORRECTION):
    """Return ([(user_a, user_b, phi, p)], n_tests) for the significant pairs.

    memberships: {user_id: set of proposal ids}. Users with an empty set are ignored.
    n_proposals: total number of proposals (n), including those nobody touched.
    """
    users = [user for user, props in memberships.items() if props]
    n_tests = len(users) * (len(users) - 1) // 2
    if n_tests == 0 or n_proposals < 2:
        return [], n_tests

    proposal_index = {}
    rows, cols = [], []
    for i, user in enumerate(users):
        for proposal in memberships[user]:
            rows.append(i)
            cols.append(proposal_index.setdefault(proposal, len(proposal_index)))
    if len(proposal_index) > n_proposals:
        raise ValueError('memberships mention more proposals than n_proposals')

    incidence = sparse.csr_matrix(
        (np.ones(len(rows), dtype=np.int64), (rows, cols)), shape=(len(users), len(proposal_index)))
    activity = np.asarray(incidence.sum(axis=1)).ravel()

    co = sparse.triu(incidence @ incidence.T, k=1).tocoo()  # pairs i < j sharing >= 1 proposal
    a, b = activity[co.row], activity[co.col]
    pvalues = overlap_pvalue(co.data, a, b, n_proposals)
    phi = phi_coefficient(co.data, a, b, n_proposals)

    # phi > 0 is implied by a small p (overlap above its expectation a*b/n);
    # it also drops pairs whose phi is undefined.
    keep = significant(pvalues, n_tests, alpha, correction) & (phi > 0)
    edges = [(users[i], users[j], float(f), float(p))
             for i, j, f, p in zip(co.row[keep], co.col[keep], phi[keep], pvalues[keep])]
    return edges, n_tests


def distinct_colors(k):
    """k distinct RGB colours, well separated for the first ones.

    Hues follow the golden-ratio sequence, cycling through a few saturation and
    brightness levels. Colours must be unique because the API uses them as
    community keys (/stats/<kind>/colors).
    """
    golden = (5 ** 0.5 - 1) / 2
    levels = [(0.65, 0.90), (0.90, 0.70), (0.45, 0.80), (0.80, 0.55)]
    colors, used = [], set()
    for i in range(k):
        saturation, value = levels[(i // 8) % len(levels)]
        r, g, b = (round(255 * c) for c in colorsys.hsv_to_rgb((i * golden) % 1.0, saturation, value))
        while (r, g, b) in used:  # rare rounding collision: nudge until unique
            b = (b + 1) % 256
            if b == 0:
                g = (g + 1) % 256
        used.add((r, g, b))
        colors.append((r, g, b))
    return colors


def to_hex(rgb):
    return '#{:02x}{:02x}{:02x}'.format(*rgb)


def build_network(memberships, n_proposals, usernames, alpha=DEFAULT_ALPHA, correction=DEFAULT_CORRECTION,
                  seed=DEFAULT_SEED):
    """Build the network, detect communities and lay it out.

    Returns the JSON-serialisable dict served by /stats/comments and
    /stats/endorsements. The keys of the original API are kept
    ('users', 'positions', 'usernames', 'colors'); 'communities', 'modularity'
    and 'parameters' are new.
    """
    active = [user for user, props in memberships.items() if props]

    graph = nx.Graph()
    graph.add_nodes_from(active)
    edges, n_tests = phi_edges(memberships, n_proposals, alpha, correction)
    for a, b, phi, p in edges:
        graph.add_edge(a, b, phi=phi, p=p)

    communities = nx.community.louvain_communities(graph, weight='phi', seed=seed) if active else []
    communities = sorted(communities, key=lambda c: (-len(c), min(c)))
    modularity = nx.community.modularity(graph, communities, weight='phi') if graph.number_of_edges() else 0.0

    node_community = {node: i for i, community in enumerate(communities) for node in community}
    community_colors = distinct_colors(len(communities))

    positions, layout = network_layout(graph, communities, seed)

    adjacency = defaultdict(dict)
    for node in active:
        adjacency[node] = {}
    for a, b, data in graph.edges(data=True):
        adjacency[a][b] = data['phi']
        adjacency[b][a] = data['phi']

    return {
        'users': dict(adjacency),
        'positions': positions,
        'usernames': {node: usernames.get(node, '') for node in active},
        'colors': {node: community_colors[node_community[node]] for node in active},
        'communities': node_community,
        'modularity': modularity,
        'parameters': {
            'n_proposals': n_proposals,
            'n_users': len(active),
            'n_edges': graph.number_of_edges(),
            'n_tests': n_tests,
            'test': 'hypergeometric (one-sided)',
            'alpha': alpha,
            'correction': correction,
            'seed': seed,
            'layout': layout,
        },
    }


MAX_SPRING_LAYOUT_NODES = 5000


def _ring(nodes, radius):
    return {node: [radius * cos(2 * pi * k / len(nodes)), radius * sin(2 * pi * k / len(nodes))]
            for k, node in enumerate(nodes)}


def network_layout(graph, communities, seed=DEFAULT_SEED):
    """Node positions for drawing, and the name of the layout used.

    Connected users get a force-directed (Fruchterman-Reingold) layout with phi
    as the edge weight, so strongly linked users end up close together; users
    without any edge are put on a ring around them. Above
    MAX_SPRING_LAYOUT_NODES connected users the force-directed layout gets
    slow (quadratic per iteration), so everyone is placed on a circle instead,
    with each community as a contiguous arc.
    """
    order = {node: i for i, community in enumerate(communities) for node in community}
    by_community = lambda nodes: sorted(nodes, key=lambda node: (order.get(node, 0), node))
    connected = [node for node in graph if graph.degree(node) > 0]
    isolated = by_community(node for node in graph if graph.degree(node) == 0)

    if not connected or len(connected) > MAX_SPRING_LAYOUT_NODES:
        return _ring(by_community(graph.nodes), 1.0), 'circular'

    spring = nx.spring_layout(graph.subgraph(connected), weight='phi', seed=seed)
    # spring_layout bounds each axis, so corners can reach sqrt(2); scale to the
    # unit disc to keep the connected users inside the ring of isolated ones.
    furthest = max((x * x + y * y) ** 0.5 for x, y in spring.values()) or 1.0
    positions = {node: [float(x) / furthest, float(y) / furthest] for node, (x, y) in spring.items()}
    if isolated:
        positions.update(_ring(isolated, 1.25))
    return positions, 'spring'
