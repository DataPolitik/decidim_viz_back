import csv
from datetime import datetime

from django.core.management.base import BaseCommand

from stats.models import Proposal, User, Category


class Command(BaseCommand):
    help = 'Import data from csv file into the SQL database.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)

    def handle(self, *args, **options):
        csv_path = options['csv_path']

        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file, delimiter=';')

            for row in reader:
                proposal_to_add = Proposal()
                proposal_to_add.id_proposal = row['id']
                proposal_to_add.proposal_title_es = row['title/machine_translations/es']
                proposal_to_add.proposal_title_en = row['title/machine_translations/en']
                proposal_to_add.proposal_title_fr = row['title/machine_translations/fr']
                proposal_to_add.published_at = datetime.strptime(row['published_at'], '%Y-%m-%d %H:%M:%S %Z')
                proposal_to_add.endorsements = len(row['endorsements/user_endorsements'].split(','))
                if row['category/id'] != '':
                    if Category.objects.filter(id=row['category/id']).exists():
                        proposal_to_add.category = Category.objects.get(id=row['category/id'])
                    else:
                        category_to_add = Category(id=row['category/id'])
                        category_to_add.name_es = row['category/name/es']
                        category_to_add.name_en = row['category/name/en']
                        category_to_add.save()
                        proposal_to_add.category = category_to_add
                proposal_to_add.save()

                users = row['endorsements/user_endorsements'].split(',')
                for user in users:
                    user_trimmed = user.strip()
                    if len(user_trimmed) > 0:
                        if not User.objects.filter(name=user_trimmed).exists():
                            user_to_add = User()
                            user_to_add.name = user_trimmed
                            user_to_add.save()
                            proposal_to_add.users.add(user_to_add)

        self.stdout.write('There are {} proposals!'.format(Proposal.objects.count()))
        self.stdout.write('There are {} users!'.format(User.objects.count()))
