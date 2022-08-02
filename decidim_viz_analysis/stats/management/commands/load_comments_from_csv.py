import csv

from django.core.management.base import BaseCommand

from stats.models import Proposal, User, Comment

class Command(BaseCommand):
    help = 'Import data from csv file into the SQL database.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)

    def handle(self, *args, **options):
        csv_path = options['csv_path']

        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file, delimiter=';')

            for row in reader:
                commment_to_add = Comment()
                commment_to_add.id_comment = row['id']
                commment_to_add.depth = row['depth']
                commment_to_add.language = row['locale']
                if not User.objects.filter(name=row['author/name']).exists():
                    user_to_add = User()
                    user_to_add.name = row['author/name']
                    user_to_add.save()
                else:
                    user_to_add = User.objects.get(name=row['author/name'])
                commment_to_add.author = user_to_add
                if int(row['depth']) > 0:
                    replied_comment = Comment.objects.get(pk=row['commentable_id'])
                    commment_to_add.reply_to = replied_comment
                    commment_to_add.proposal_replied = replied_comment.proposal_replied
                    commment_to_add.save()
                    replied_comment.comments.add(commment_to_add)
                    replied_comment.save()

                else:
                    replied_proposal = Proposal.objects.get(id_proposal=row['commentable_id'])
                    commment_to_add.proposal_replied = replied_proposal
                    commment_to_add.save()
                replied_proposal.comments.add(commment_to_add)
                replied_proposal.save()

        self.stdout.write('There are {} comments!'.format(Comment.objects.count()))
