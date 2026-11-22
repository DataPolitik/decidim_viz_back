"""Comment and endorsement networks: data extraction from the database and caching."""
import pickle
from collections import defaultdict
from pathlib import Path

from django.conf import settings

from stats.models import Comment, Proposal, User
from stats.phi.phi import DEFAULT_ALPHA, DEFAULT_CORRECTION, DEFAULT_SEED, build_network

CACHE_FILES = {
    'comments': 'comments_all.pickle',
    'endorsements': 'endorsement_all.pickle',
}


def comment_memberships():
    """{user_id: set of proposals the user commented on}"""
    memberships = defaultdict(set)
    for user_id, proposal_id in Comment.objects.values_list('author_id', 'proposal_replied_id'):
        memberships[user_id].add(proposal_id)
    return memberships


def endorsement_memberships():
    """{user_id: set of proposals the user endorsed}"""
    memberships = defaultdict(set)
    for user_id, proposal_id in Proposal.users.through.objects.values_list('user_id', 'proposal_id'):
        memberships[user_id].add(proposal_id)
    return memberships


MEMBERSHIPS = {
    'comments': comment_memberships,
    'endorsements': endorsement_memberships,
}


def compute_network(kind, alpha=DEFAULT_ALPHA, correction=DEFAULT_CORRECTION, seed=DEFAULT_SEED):
    memberships = MEMBERSHIPS[kind]()
    usernames = dict(User.objects.filter(id__in=list(memberships)).values_list('id', 'name'))
    return build_network(memberships, Proposal.objects.count(), usernames,
                         alpha=alpha, correction=correction, seed=seed)


def cache_path(kind):
    return Path(settings.DECIDIM_VIZ_CACHE_DIR) / CACHE_FILES[kind]


def write_cache(network, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'wb') as handle:
        pickle.dump(network, handle, protocol=pickle.HIGHEST_PROTOCOL)


def get_network(kind):
    """Return the cached network, computing and caching it on first use.

    Precompute it with `manage.py generate_comments_cache` /
    `generate_endorses_cache` on large instances, and re-run them after
    importing new data (the cache is not invalidated automatically).
    """
    path = cache_path(kind)
    if path.exists():
        with open(path, 'rb') as handle:
            return pickle.load(handle)
    network = compute_network(kind)
    write_cache(network, path)
    return network
