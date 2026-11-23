import csv
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from stats.csv_utils import blank_to_none, first_filled, parse_datetime, split_names
from stats.models import Category, Proposal
from stats.users import UserResolver


class Command(BaseCommand):
    help = 'Import proposals and their endorsements from a Decidim proposals CSV export (";"-separated).'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)

    @transaction.atomic
    def handle(self, *args, **options):
        users = UserResolver()

        with open(options['csv_path'], 'r', encoding='utf-8') as file:
            for row in csv.DictReader(file, delimiter=';'):
                # Endorsements were renamed "likes" in newer Decidim versions.
                endorsers = split_names(first_filled(row, ('endorsements/user_endorsements', 'likes/user_likes')))

                proposal, _ = Proposal.objects.update_or_create(
                    id_proposal=int(row['id']),
                    defaults={
                        'proposal_title_es': self._title(row, 'es'),
                        'proposal_title_en': self._title(row, 'en'),
                        'proposal_title_fr': self._title(row, 'fr'),
                        'proposal_title': self._original_title(row),
                        # The proposal's own page; older exports may only have the space's.
                        'url': blank_to_none(first_filled(row, ('url', 'participatory_space/url'))),
                        'latitude': blank_to_none(row.get('latitude')),
                        'longitude': blank_to_none(row.get('longitude')),
                        'published_at': parse_datetime(row.get('published_at')),
                        'endorsements': len(endorsers),
                        'category': self._category(row),
                    },
                )

                # The same name twice on one proposal means two different people.
                for name, count in Counter(endorsers).items():
                    if count > 1:
                        users.mark_ambiguous(name)
                proposal.users.add(*{users.endorser(name) for name in endorsers})

        users.reconcile()
        self.stdout.write('There are {} proposals!'.format(Proposal.objects.count()))
        self.stdout.write(users.summary())

    @staticmethod
    def _original_title(row):
        # Any title/<language> column holds text as written; fall back to machine translations.
        written = [c for c in row if c.startswith('title/') and not c.startswith('title/machine_translations/')]
        translated = [c for c in row if c.startswith('title/machine_translations/')]
        return first_filled(row, written + translated)

    @staticmethod
    def _title(row, language):
        # Text written in that language, else Decidim's machine translation.
        return first_filled(row, ('title/{}'.format(language), 'title/machine_translations/{}'.format(language)))

    @staticmethod
    def _category(row):
        category_id = (row.get('category/id') or '').strip()
        prefix = 'category/name'
        if not category_id:
            # Newer Decidim versions replaced categories with taxonomies; a
            # proposal may have several, and its first one is used.
            taxonomy_ids = [t.strip() for t in (row.get('taxonomies/ids') or '').split(',') if t.strip()]
            if not taxonomy_ids:
                return None
            category_id, prefix = taxonomy_ids[0], 'taxonomies/{}'.format(taxonomy_ids[0])
        category, _ = Category.objects.get_or_create(
            id=int(category_id),
            defaults={
                'name_es': blank_to_none(row.get('{}/es'.format(prefix))),
                'name_ca': blank_to_none(row.get('{}/ca'.format(prefix))),
                'name_en': blank_to_none(row.get('{}/en'.format(prefix))),
            },
        )
        return category
