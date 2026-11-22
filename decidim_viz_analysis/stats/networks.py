"""Comment and endorsement networks: data extraction from the database and caching."""
import pickle
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings

from stats.models import Comment, Proposal, User
from stats.phi.phi import DEFAULT_ALPHA, DEFAULT_CORRECTION, DEFAULT_SEED, build_network, to_hex

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


TITLE_FIELDS = {
    'en': ('proposal_title_en', 'proposal_title_es', 'proposal_title_fr'),
    'es': ('proposal_title_es', 'proposal_title_en', 'proposal_title_fr'),
    'fr': ('proposal_title_fr', 'proposal_title_en', 'proposal_title_es'),
}


def community_colors(kind, n_proposals=3, language='en'):
    """Communities of the cached network, keyed by their colour.

    Shape expected by the front end's Interactions page:

        {'total': number of users in the network,
         'colors': {'users':     {'#rrggbb': [user ids]},
                    'proposals': {'#rrggbb': {proposal title: members who took part}}}}

    Communities are listed from largest to smallest. For each one, the
    n_proposals proposals with the most participating members are given.
    """
    network = get_network(kind)
    title_fields = TITLE_FIELDS.get(language, TITLE_FIELDS['en'])

    members = defaultdict(list)  # colour -> user ids
    for user, rgb in network['colors'].items():
        members[to_hex(rgb)].append(user)
    members = dict(sorted(members.items(), key=lambda item: (-len(item[1]), item[0])))

    memberships = MEMBERSHIPS[kind]()
    top_proposals = {}
    for color, users in members.items():
        counts = Counter(proposal for user in users for proposal in memberships.get(user, ()))
        top_proposals[color] = counts.most_common(n_proposals)

    proposal_ids = {proposal for top in top_proposals.values() for proposal, _ in top}
    titles = {}
    for row in Proposal.objects.filter(id_proposal__in=proposal_ids).values('id_proposal', *title_fields):
        titles[row['id_proposal']] = next((row[field] for field in title_fields if row[field]),
                                          '#{}'.format(row['id_proposal']))

    proposals = {}
    for color, top in top_proposals.items():
        proposals[color] = {}
        for proposal, count in top:
            title = titles.get(proposal, '#{}'.format(proposal))
            if title in proposals[color]:  # two proposals with the same title
                title = '{} (#{})'.format(title, proposal)
            proposals[color][title] = count

    return {
        'total': len(network['colors']),
        'colors': {'users': members, 'proposals': proposals},
    }
