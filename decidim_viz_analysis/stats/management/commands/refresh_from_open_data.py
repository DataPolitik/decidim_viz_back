import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

DOWNLOAD_TIMEOUT_SECONDS = 600


def find_member(names, suffix, exclude=None):
    """The first zip member whose name ends with suffix (and not with exclude)."""
    for name in names:
        if name.endswith(suffix) and not (exclude and name.endswith(exclude)):
            return name
    return None


class Command(BaseCommand):
    help = ("Download a Decidim instance's open-data export, import its proposals and comments, "
            "and rebuild the networks. Meant to run as a scheduled task.")

    def add_arguments(self, parser):
        parser.add_argument('source', help=(
            'The instance address (e.g. https://meta.decidim.org; its /open-data/download is fetched), '
            'a direct URL to the zip, or a local zip file.'))

    def handle(self, *args, **options):
        source = options['source']
        workdir = Path(tempfile.mkdtemp(prefix='decidim-viz-'))
        try:
            archive = self._get_archive(source, workdir)
            proposals, comments = self._extract(archive, workdir)

            call_command('load_endorses_from_csv', str(proposals), stdout=self.stdout, stderr=self.stderr)
            if comments:
                call_command('load_comments_from_csv', str(comments), stdout=self.stdout, stderr=self.stderr)
            else:
                self.stderr.write('The export has no proposal comments; only proposals and endorsements were imported.')
            call_command('generate_endorses_cache', stdout=self.stdout)
            call_command('generate_comments_cache', stdout=self.stdout)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def _get_archive(self, source, workdir):
        local = Path(source)
        if local.is_file():
            return local
        url = source if source.lower().split('?')[0].endswith('.zip') or source.startswith('file:') \
            else source.rstrip('/') + '/open-data/download'
        self.stdout.write('Downloading {}'.format(url))
        target = workdir / 'open-data.zip'
        request = urllib.request.Request(url, headers={'User-Agent': 'decidim-viz (open-data refresh)'})
        try:
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response, \
                    open(target, 'wb') as out:
                shutil.copyfileobj(response, out)
        except OSError as error:
            raise CommandError('Could not download {}: {}'.format(url, error))
        return target

    def _extract(self, archive, workdir):
        try:
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
                proposals = find_member(names, 'proposals.csv', exclude='_proposals.csv')
                comments = find_member(names, 'proposal_comments.csv')
                if not proposals:
                    raise CommandError('No proposals CSV in the export (files: {})'.format(', '.join(names)))
                extracted = []
                for name in (proposals, comments):
                    if name:
                        target = workdir / Path(name).name
                        with zf.open(name) as source, open(target, 'wb') as out:
                            shutil.copyfileobj(source, out)
                        extracted.append(target)
                    else:
                        extracted.append(None)
                return extracted[0], extracted[1]
        except zipfile.BadZipFile:
            raise CommandError('{} is not a zip file'.format(archive))
