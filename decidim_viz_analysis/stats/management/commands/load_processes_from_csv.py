import csv
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from stats.csv_utils import blank_to_none
from stats.models import ParticipatoryProcess


def parse_day(value):
    """A day from an export cell ("2021-11-04", possibly with a time); None if blank or invalid."""
    value = (value or '').strip()[:10]
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def titles_of(row):
    """Title per locale: written titles, then Decidim's machine translations for the missing ones."""
    titles = {}
    for column, text in row.items():
        text = (text or '').strip()
        if text and column.startswith('title/') and not column.startswith('title/machine_translations/'):
            titles[column.split('/', 1)[1]] = text
    for column, text in row.items():
        text = (text or '').strip()
        if text and column.startswith('title/machine_translations/'):
            titles.setdefault(column.rsplit('/', 1)[1], text)
    return titles


class Command(BaseCommand):
    help = 'Import participatory processes (titles, start and end dates) from a Decidim export (";"-separated).'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)

    @transaction.atomic
    def handle(self, *args, **options):
        csv.field_size_limit(2 ** 31 - 1)  # descriptions can be long
        with open(options['csv_path'], 'r', encoding='utf-8') as file:
            for row in csv.DictReader(file, delimiter=';'):
                ParticipatoryProcess.objects.update_or_create(
                    id_process=int(row['id']),
                    defaults={
                        'titles': titles_of(row),
                        'slug': blank_to_none(row.get('slug')),
                        'start_date': parse_day(row.get('start_date')),
                        'end_date': parse_day(row.get('end_date')),
                        'url': blank_to_none(row.get('url')),
                    },
                )
        self.stdout.write('There are {} participatory processes!'.format(ParticipatoryProcess.objects.count()))
