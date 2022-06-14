from django.db import models


class User(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Comment(models.Model):
    id_comment = models.IntegerField(primary_key=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    comments = models.ManyToManyField('self')
    reply_to = models.ForeignKey('self', on_delete=models.CASCADE, null=True)
    proposal_replied = models.ForeignKey(to='stats.Proposal', on_delete=models.CASCADE)
    depth = models.IntegerField(primary_key=False, null=False, default=0)

    class Meta:
        ordering = ['id_comment']

    def __str__(self):
        return str(self.id_comment)


class Proposal(models.Model):
    id_proposal = models.IntegerField(primary_key=True)
    proposal_title_es = models.CharField(max_length=255)
    proposal_title_en = models.CharField(max_length=255)
    proposal_title_fr = models.CharField(max_length=255)
    users = models.ManyToManyField(User)
    comments = models.ManyToManyField(Comment)

    class Meta:
        ordering = ['id_proposal']

    def __str__(self):
        return str(self.id_proposal)
