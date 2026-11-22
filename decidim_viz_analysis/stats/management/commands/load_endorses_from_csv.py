import csv

from django.core.management.base import BaseCommand
from django.db import transaction

from stats.csv_utils import blank_to_none, parse_datetime, split_names
from stats.models import Category, Proposal, User


class Command(BaseCommand):
    help = 'Import proposals and their endorsements from a Decidim proposals CSV export (";"-separated).'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)

    @transaction.atomic
    def handle(self, *args, **options):
        users_by_name = {user.name: user for user in User.objects.all()}

        with open(options['csv_path'], 'r', encoding='utf-8') as file:
            for row in csv.DictReader(file, delimiter=';'):
                endorsers = split_names(row.get('endorsements/user_endorsements'))

                proposal, _ = Proposal.objects.update_or_create(
                    id_proposal=int(row['id']),
                    defaults={
                        'proposal_title_es': row.get('title/machine_translations/es', ''),
                        'proposal_title_en': row.get('title/machine_translations/en', ''),
                        'proposal_title_fr': row.get('title/machine_translations/fr', ''),
                        'url': blank_to_none(row.get('participatory_space/url')),
                        'latitude': blank_to_none(row.get('latitude')),
                        'longitude': blank_to_none(row.get('longitude')),
                        'published_at': parse_datetime(row.get('published_at')),
                        'endorsements': len(endorsers),
                        'category': self._category(row),
                    },
                )

                for name in endorsers:
                    if name not in users_by_name:
                        users_by_name[name] = User.objects.create(name=name)
                proposal.users.add(*(users_by_name[name] for name in endorsers))

        self.stdout.write('There are {} proposals!'.format(Proposal.objects.count()))
        self.stdout.write('There are {} users!'.format(User.objects.count()))

    @staticmethod
    def _category(row):
        category_id = (row.get('category/id') or '').strip()
        if not category_id:
            return None
        category, _ = Category.objects.get_or_create(
            id=int(category_id),
            defaults={
                'name_es': blank_to_none(row.get('category/name/es')),
                'name_ca': blank_to_none(row.get('category/name/ca')),
                'name_en': blank_to_none(row.get('category/name/en')),
            },
        )
        return category
