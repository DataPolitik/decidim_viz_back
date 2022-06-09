from django.db import models


class Proposal(models.Model):
    id_proposal = models.IntegerField(primary_key=True)
    proposal_title_es = models.CharField(max_length=255)
    proposal_title_en = models.CharField(max_length=255)
    proposal_title_fr = models.CharField(max_length=255)

    def __str__(self):
        return str(self.id_proposal)


class User(models.Model):
    name = models.CharField(max_length=50, unique=True)
    supports = models.ManyToManyField(Proposal)

    def __str__(self):
        return self.name
