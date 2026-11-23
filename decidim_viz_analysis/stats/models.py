from django.db import models


class User(models.Model):
    """A Decidim participant, or a display name that could not be tied to one.

    - decidim_id set: an identified participant (from the comments export).
    - decidim_id null: a name-only record, created for endorsers, since the
      proposals export lists endorsers by display name only. See stats/users.py.
    - ambiguous: the record is known to stand for more than one person (or for
      unknown authors); it is excluded from the networks.
    """
    name = models.CharField(max_length=255, db_index=True)
    decidim_id = models.IntegerField(null=True, blank=True, unique=True)
    ambiguous = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Category(models.Model):
    name_es = models.CharField(max_length=512, null=True)
    name_ca = models.CharField(max_length=512, null=True)
    name_en = models.CharField(max_length=512, null=True)


class Comment(models.Model):
    id_comment = models.IntegerField(primary_key=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    language = models.CharField(max_length=4, null=True)
    created_at = models.DateTimeField(null=True)
    # The comment this one answers (null for top-level comments); comment.replies are its answers.
    reply_to = models.ForeignKey('self', on_delete=models.CASCADE, null=True, related_name='replies')
    proposal_replied = models.ForeignKey(to='stats.Proposal', on_delete=models.CASCADE)
    depth = models.IntegerField(primary_key=False, null=False, default=0)
    # Length in characters of the comment text (the text itself is not stored).
    body_length = models.IntegerField(null=True)

    class Meta:
        ordering = ['id_comment']

    def __str__(self):
        return str(self.id_comment)


class Proposal(models.Model):
    id_proposal = models.IntegerField(primary_key=True)
    proposal_title_es = models.CharField(max_length=255)
    proposal_title_en = models.CharField(max_length=255)
    proposal_title_fr = models.CharField(max_length=255)
    # Title as written, in whatever language the proposal was published in.
    proposal_title = models.TextField(blank=True, default='')
    published_at = models.DateTimeField(null=True)
    url = models.CharField(max_length=300, null=True)
    latitude = models.CharField(max_length=50, null=True)
    longitude = models.CharField(max_length=50, null=True)
    endorsements = models.IntegerField(null=False, default=0)
    category = models.ForeignKey(Category, on_delete=models.RESTRICT, null=True)
    users = models.ManyToManyField(User)
    comments = models.ManyToManyField(Comment)

    class Meta:
        ordering = ['id_proposal']

    def __str__(self):
        return str(self.id_proposal)

    @property
    def display_title(self):
        """A title in any language: the original, else a translation, else the id."""
        return (self.proposal_title or self.proposal_title_en or self.proposal_title_es
                or self.proposal_title_fr or '#{}'.format(self.id_proposal))
