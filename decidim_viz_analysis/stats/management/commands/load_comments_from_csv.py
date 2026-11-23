import csv

from django.core.management.base import BaseCommand
from django.db import transaction

from stats.csv_utils import blank_to_none, parse_datetime
from stats.models import Comment, Proposal
from stats.users import UserResolver


class Command(BaseCommand):
    help = ('Import comments from a Decidim comments CSV export (";"-separated). '
            'Load the proposals first with load_endorses_from_csv.')

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)

    @transaction.atomic
    def handle(self, *args, **options):
        with open(options['csv_path'], 'r', encoding='utf-8') as file:
            rows = list(csv.DictReader(file, delimiter=';'))

        # A reply can only be linked once its parent exists, so load by depth.
        rows.sort(key=lambda row: int(row.get('depth') or 0))

        users = UserResolver()
        skipped = 0

        for row in rows:
            depth = int(row.get('depth') or 0)
            parent = None

            if depth > 0:
                # For replies, commentable_id is the parent comment.
                parent = Comment.objects.filter(pk=int(row['commentable_id'])).first()
                if parent is None:
                    skipped += 1
                    continue
                proposal = parent.proposal_replied
            else:
                proposal = Proposal.objects.filter(id_proposal=self._proposal_id(row)).first()
                if proposal is None:
                    skipped += 1
                    continue

            author_id = (row.get('author/id') or '').strip()
            author = users.commenter(int(author_id) if author_id else None, row.get('author/name'))

            comment, _ = Comment.objects.update_or_create(
                id_comment=int(row['id']),
                defaults={
                    'author': author,
                    'depth': depth,
                    'language': blank_to_none(row.get('locale')),
                    'created_at': parse_datetime(row.get('created_at')),
                    'reply_to': parent,
                    'proposal_replied': proposal,
                    # Only the length of the text is kept.
                    'body_length': len(row['body']) if row.get('body') is not None else None,
                },
            )
            proposal.comments.add(comment)

        users.reconcile()
        self.stdout.write('There are {} comments!'.format(Comment.objects.count()))
        self.stdout.write(users.summary())
        if skipped:
            self.stderr.write('Skipped {} comments whose proposal or parent comment was not found.'.format(skipped))

    @staticmethod
    def _proposal_id(row):
        # root_commentable_id is always the proposal; fall back to commentable_id
        # for exports that lack it (top-level comments point at the proposal).
        return int((row.get('root_commentable_id') or row['commentable_id']).strip())
