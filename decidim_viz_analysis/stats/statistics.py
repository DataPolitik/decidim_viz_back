"""Descriptive statistics behind the front end's Statistics and Activity pages.

People are counted without the ambiguous user records (see stats/users.py),
which stand for several people or for unknown authors.
"""
from collections import Counter
from urllib.parse import urlparse

import numpy as np
from django.db.models import Count, Max, Min, Q

from stats.models import Comment, ParticipatoryProcess, Proposal, User


def gini(values):
    """Gini coefficient of non-negative values, and each value's contribution to it.

    G = sum_i sum_j |x_i - x_j| / (2 n^2 mean). The contribution of item i is
    sum_j |x_i - x_j| / (2 n^2 mean), so the contributions add up to G. They
    are returned in the order of ``values``. All zeros or no values give 0.
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n == 0 or x.sum() == 0:
        return 0.0, [0.0] * n
    order = np.argsort(x, kind='stable')
    sorted_x = x[order]
    before = np.concatenate(([0.0], np.cumsum(sorted_x)[:-1]))  # sum of the values ranked lower
    rank = np.arange(n)
    # sum_j |x_i - x_j| for each sorted x_i: lower ones contribute x_i - x_j, higher ones x_j - x_i.
    abs_diff_sorted = sorted_x * rank - before + (sorted_x.sum() - before - sorted_x) - sorted_x * (n - rank - 1)
    contributions = np.empty(n)
    contributions[order] = abs_diff_sorted / (2 * n * n * x.mean())
    return float(contributions.sum()), contributions.tolist()


def gini_for(values, listed):
    """{'value', 'contributions'} for the whole population ``values`` (a dict
    key -> value), with the contributions of the ``listed`` keys, in order."""
    keys = list(values)
    value, contributions = gini([values[key] for key in keys])
    by_key = dict(zip(keys, contributions))
    return {'value': value, 'contributions': [by_key.get(key, 0.0) for key in listed]}


def _people():
    return User.objects.filter(ambiguous=False)


def _comments():
    return Comment.objects.filter(author__ambiguous=False)


def temporal_limits():
    """First and last publication dates of proposals and comments (ISO 8601, or None)."""
    proposals = Proposal.objects.aggregate(first=Min('published_at'), last=Max('published_at'))
    comments = Comment.objects.aggregate(first=Min('created_at'), last=Max('created_at'))
    iso = lambda moment: moment.isoformat() if moment else None
    return {
        'proposals_from': iso(proposals['first']),
        'proposals_to': iso(proposals['last']),
        'comments_from': iso(comments['first']),
        'comments_to': iso(comments['last']),
    }


def processes(language='en'):
    """The instance's participatory processes, earliest first: {'processes': [...]}.

    Each has its id, title (in language, else English, else any), start_date and
    end_date ("YYYY-MM-DD" or None) and its page on Decidim (url).
    """
    return {'processes': [
        {
            'id': process.id_process,
            'title': process.title_in(language),
            'start_date': process.start_date.isoformat() if process.start_date else None,
            'end_date': process.end_date.isoformat() if process.end_date else None,
            'url': process.url,
        }
        for process in ParticipatoryProcess.objects.all()
    ]}


def instance():
    """The Decidim instance the imported data come from, read from the proposals' URLs.

    The most common host is reported; 'hosts' lists every host with its number
    of proposals, so a database mixing several instances is visible. api_url
    is Decidim's GraphQL endpoint, which is always at /api. Without proposals
    (or URLs), name, url and api_url are None.
    """
    hosts = Counter()
    schemes = {}
    for url in Proposal.objects.exclude(url=None).exclude(url='').values_list('url', flat=True):
        parsed = urlparse(url)
        if parsed.netloc:
            hosts[parsed.netloc] += 1
            schemes.setdefault(parsed.netloc, parsed.scheme or 'https')
    if not hosts:
        return {'name': None, 'url': None, 'api_url': None, 'hosts': []}
    name = hosts.most_common(1)[0][0]
    url = '{}://{}'.format(schemes[name], name)
    return {
        'name': name,
        'url': url,
        'api_url': url + '/api',
        'hosts': [{'name': host, 'proposals': count} for host, count in hosts.most_common()],
    }


def summary():
    """Headline counts: people who commented or endorsed, proposals and comments."""
    participants = _people().filter(Q(id__in=_comments().values('author_id')) |
                                    Q(id__in=Proposal.users.through.objects.values('user_id')))
    return {
        'participants': participants.count(),
        'proposals': Proposal.objects.count(),
        'comments': Comment.objects.count(),
    }


def participation_types():
    """How many people only comment, only endorse, do both ('all'), or neither ('inactive')."""
    people = set(_people().values_list('id', flat=True))
    commenters = set(_comments().values_list('author_id', flat=True)) & people
    endorsers = set(Proposal.users.through.objects.values_list('user_id', flat=True)) & people
    return {
        'comments': len(commenters - endorsers),
        'endorsements': len(endorsers - commenters),
        'all': len(commenters & endorsers),
        'inactive': len(people - commenters - endorsers),
    }


def comments_per_user():
    """{user id: number of comments}, for people with at least one comment."""
    return Counter(_comments().values_list('author_id', flat=True))


def top_commenters(limit):
    counts = comments_per_user()
    top = counts.most_common(limit)
    names = dict(User.objects.filter(id__in=[user for user, _ in top]).values_list('id', 'name'))
    return {
        'comments': [{'id': str(user), 'name': names.get(user, ''), 'comments': count} for user, count in top],
        'gini': gini_for(counts, [user for user, _ in top]),
    }


def comment_lengths():
    """Length in characters of each comment whose text was imported."""
    return list(Comment.objects.exclude(body_length=None).values_list('body_length', flat=True))


def comment_depths():
    """Depth of each comment: 0 for comments on a proposal, 1 for a reply to those, and so on."""
    return list(Comment.objects.values_list('depth', flat=True))


def proposals_with_and_without_comments():
    with_comments = Proposal.objects.filter(comment__isnull=False).distinct().count()
    return {'0': Proposal.objects.count() - with_comments, '>0': with_comments}


def hours_to_first_comment():
    """Hours from each commented proposal's publication to its first comment.

    Proposals without a publication date, and the few whose first comment
    predates publication (drafts and imported data), are left out.
    """
    rows = (Proposal.objects.exclude(published_at=None)
            .annotate(first_comment=Min('comment__created_at'))
            .exclude(first_comment=None)
            .values_list('published_at', 'first_comment'))
    hours = [(first - published).total_seconds() / 3600 for published, first in rows]
    return [h for h in hours if h >= 0]
