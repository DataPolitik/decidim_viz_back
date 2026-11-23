"""Matching the people who appear in the Decidim CSV exports.

The two exports identify people differently:

- comments: ``author/id`` and ``author/name``, so commenters are identified by
  their Decidim id and two people with the same display name stay separate;
- proposals: ``endorsements/user_endorsements`` is a list of display names only
  (in every Decidim version up to at least 0.28), so endorsers can only be
  matched by name.

Rules:

1. A commenter is the user with that Decidim id.
2. An endorser name maps to the identified user with that name when there is
   exactly one; otherwise to a name-only record (``decidim_id`` null).
3. A name-only record is merged into an identified user when, after loading,
   exactly one identified user has its name (see ``UserResolver.reconcile``).
4. A name-only record is marked ``ambiguous`` when the name is known to belong
   to several people: two or more identified users share it, or it appears
   twice in one proposal's endorsement list. Ambiguous records are never merged
   and are excluded from the networks.

Homonyms who only endorse, never comment and never endorse the same proposal
cannot be told apart from these exports; they remain a single name-only user.
"""
from collections import defaultdict

from stats.models import Comment, User

UNKNOWN_AUTHOR = '[unknown author]'


class UserResolver:
    """Resolves export rows to User records, keeping in-memory indexes for speed."""

    def __init__(self):
        self.by_decidim_id = {}
        self.identified_by_name = defaultdict(dict)  # name -> {decidim_id: User}
        self.name_only = {}                           # name -> User without decidim_id
        for user in User.objects.all():
            self._index(user)
        self.stats = defaultdict(int)

    def _index(self, user):
        if user.decidim_id is not None:
            self.by_decidim_id[user.decidim_id] = user
            self.identified_by_name[user.name][user.decidim_id] = user
        else:
            self.name_only[user.name] = user

    def commenter(self, decidim_id, name):
        """The author of a comment. Falls back to the name when the id is missing."""
        name = (name or '').strip()
        if decidim_id is None:
            return self.unknown_author() if not name else self._name_only(name)

        user = self.by_decidim_id.get(decidim_id)
        if user is None:
            user = User.objects.create(decidim_id=decidim_id, name=name)
            self._index(user)
        elif name and user.name != name:  # renamed since an earlier import
            del self.identified_by_name[user.name][decidim_id]
            user.name = name
            user.save(update_fields=['name'])
            self.identified_by_name[name][decidim_id] = user
        return user

    def endorser(self, name):
        name = name.strip()
        if name in self.name_only and self.name_only[name].ambiguous:
            return self.name_only[name]
        identified = self.identified_by_name.get(name, {})
        if len(identified) == 1:
            return next(iter(identified.values()))
        return self._name_only(name)

    def mark_ambiguous(self, name):
        user = self._name_only(name.strip())
        if not user.ambiguous:
            user.ambiguous = True
            user.save(update_fields=['ambiguous'])

    def unknown_author(self):
        user = self._name_only(UNKNOWN_AUTHOR)
        if not user.ambiguous:
            user.ambiguous = True
            user.save(update_fields=['ambiguous'])
        return user

    def _name_only(self, name):
        user = self.name_only.get(name)
        if user is None:
            user = User.objects.create(name=name)
            self._index(user)
        return user

    def reconcile(self):
        """Merge or flag name-only records now that all identified users are known."""
        for name, user in list(self.name_only.items()):
            if user.ambiguous:
                continue
            identified = self.identified_by_name.get(name, {})
            if len(identified) == 1:
                merge_user(user, next(iter(identified.values())))
                del self.name_only[name]
                self.stats['merged'] += 1
            elif len(identified) > 1:
                user.ambiguous = True
                user.save(update_fields=['ambiguous'])
                self.stats['flagged ambiguous'] += 1

    def summary(self):
        identified = len(self.by_decidim_id)
        name_only = sum(1 for user in self.name_only.values() if not user.ambiguous)
        ambiguous = sum(1 for user in self.name_only.values() if user.ambiguous)
        return ('Users: {} identified by Decidim id, {} matched by name only, {} ambiguous '
                '(excluded from networks).'.format(identified, name_only, ambiguous))


def merge_user(source, target):
    """Move all of source's endorsements and comments to target, then delete source."""
    target.proposal_set.add(*source.proposal_set.all())
    Comment.objects.filter(author=source).update(author=target)
    source.delete()
