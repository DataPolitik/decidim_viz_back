import csv

from django.core.management.base import BaseCommand

from stats.models import Proposal, User


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
                proposal_to_add.save()

                users = row['endorsements/user_endorsements'].split(',')
                for user in users:
                    user_trimmed = user.strip()
                    if len(user_trimmed) > 0:
                        if not User.objects.filter(name=user_trimmed).exists():
                            user_to_add = User()
                            user_to_add.name = user_trimmed
                            user_to_add.save()
                            user_to_add.supports.add(proposal_to_add)

        """ Do your work here """
        self.stdout.write('There are {} proposals!'.format(Proposal.objects.count()))
