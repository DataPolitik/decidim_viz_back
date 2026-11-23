import csv
import io
import os
import pickle
import tempfile
from datetime import datetime, timezone

import numpy as np
from django.core.management import call_command
from django.test import TestCase, override_settings

from stats.models import Comment, Proposal, User
from scipy.stats import fisher_exact

from stats.phi.phi import (build_network, distinct_colors, overlap_pvalue, phi_coefficient, phi_edges,
                           significant, to_hex)

PROPOSAL_COLUMNS = ['id', 'title/machine_translations/es', 'title/machine_translations/en',
                    'title/machine_translations/fr', 'participatory_space/url', 'latitude', 'longitude',
                    'published_at', 'endorsements/user_endorsements', 'category/id', 'category/name/es',
                    'category/name/en']
COMMENT_COLUMNS = ['id', 'depth', 'locale', 'created_at', 'author/id', 'author/name', 'commentable_id', 'root_commentable_id']


def write_csv(directory, name, columns, rows):
    path = os.path.join(directory, name)
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=';')
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, '') for column in columns})
    return path


def proposal_row(id_, endorsers='', **extra):
    row = {'id': id_, 'title/machine_translations/en': 'P{}'.format(id_),
           'published_at': '2022-01-0{} 10:00:00 UTC'.format(id_ % 9 + 1),
           'endorsements/user_endorsements': endorsers}
    row.update(extra)
    return row


class PhiStatisticsTests(TestCase):
    def test_phi_equals_pearson_correlation_of_binary_vectors(self):
        rng = np.random.default_rng(0)
        n = 40
        for _ in range(20):
            x = rng.random(n) < 0.3
            y = rng.random(n) < 0.4
            if x.all() or y.all() or not x.any() or not y.any():
                continue
            phi = phi_coefficient([np.sum(x & y)], [x.sum()], [y.sum()], n)
            self.assertAlmostEqual(phi[0], np.corrcoef(x, y)[0, 1])

    def test_pvalue_equals_one_sided_fisher_exact(self):
        for n11, a, b, n in [(5, 10, 10, 100), (1, 1, 1, 50), (0, 3, 4, 20), (3, 3, 30, 40), (7, 12, 9, 60)]:
            table = [[n11, a - n11], [b - n11, n - a - b + n11]]
            expected = fisher_exact(table, alternative='greater')[1]
            self.assertAlmostEqual(overlap_pvalue([n11], [a], [b], n)[0], expected)

    def test_single_shared_proposal_has_p_one_over_n(self):
        self.assertAlmostEqual(overlap_pvalue([1], [1], [1], 5000)[0], 1 / 5000)

    def test_undefined_phi_is_nan(self):
        phi = phi_coefficient([3], [3], [10], 10)  # second user took part in every proposal
        self.assertTrue(np.isnan(phi[0]))


class CorrectionTests(TestCase):
    def test_bonferroni(self):
        mask = significant([0.001, 0.01, 0.2], n_tests=10, alpha=0.05, correction='bonferroni')
        self.assertEqual(mask.tolist(), [True, False, False])

    def test_benjamini_hochberg_step_up(self):
        # Thresholds k * 0.05 / 5 = 0.01 ... 0.05. The largest k with p_(k) <= threshold is 4,
        # so 0.035 passes although it is above its own threshold 0.03 (step-up procedure).
        mask = significant([0.035, 0.001, 0.04, 0.3, 0.015], n_tests=5, alpha=0.05, correction='fdr')
        self.assertEqual(mask.tolist(), [True, True, True, False, True])

    def test_untested_pairs_count_in_m(self):
        self.assertTrue(significant([0.01], n_tests=1, correction='fdr')[0])
        self.assertFalse(significant([0.01], n_tests=1000, correction='fdr')[0])


class PhiEdgesTests(TestCase):
    def test_only_significant_positive_pairs_become_edges(self):
        memberships = {
            'a': set(range(0, 10)),
            'b': set(range(0, 10)),     # same as a -> strong positive
            'c': set(range(10, 20)),    # disjoint from a -> negative phi
            'd': {0, 10, 20, 30},       # weak overlap with everybody
        }
        edges, n_tests = phi_edges(memberships, n_proposals=100)
        self.assertEqual(n_tests, 6)
        edges = {frozenset((u, v)): phi for u, v, phi, _ in edges}
        self.assertIn(frozenset('ab'), edges)
        self.assertAlmostEqual(edges[frozenset('ab')], 1.0)
        self.assertNotIn(frozenset('ac'), edges)
        self.assertNotIn(frozenset('bc'), edges)
        self.assertTrue(all(phi > 0 for phi in edges.values()))

    def test_random_data_gives_almost_no_edges(self):
        # Regression: the old test `t > 0.5 or t < 0.5` linked every pair.
        rng = np.random.default_rng(1)
        memberships = {u: set(rng.choice(200, size=8, replace=False).tolist()) for u in range(60)}
        edges, _ = phi_edges(memberships, n_proposals=200)
        self.assertLessEqual(len(edges), 2)

    def test_lone_shared_proposal(self):
        # p = 1/5000: significant without correction at 0.05, not at 1e-6.
        memberships = {'a': {0}, 'b': {0}, 'c': {1}}
        self.assertEqual(len(phi_edges(memberships, 5000, correction='none')[0]), 1)
        self.assertEqual(len(phi_edges(memberships, 5000, alpha=1e-6, correction='none')[0]), 0)

    def test_alpha_is_applied(self):
        memberships = {'a': {0, 1, 2, 3}, 'b': {0, 1, 4, 5}}
        self.assertTrue(phi_edges(memberships, 50, alpha=0.5, correction='none')[0])
        self.assertFalse(phi_edges(memberships, 50, alpha=1e-6, correction='none')[0])


class BuildNetworkTests(TestCase):
    def test_two_groups_give_two_communities(self):
        group_1 = {u: set(range(0, 10)) - {u} for u in range(0, 5)}
        group_2 = {u: set(range(10, 20)) - {u} for u in range(10, 15)}
        memberships = {**group_1, **group_2, 99: set()}  # 99 is inactive and must be dropped
        network = build_network(memberships, 100, {u: 'user{}'.format(u) for u in memberships})

        self.assertEqual(set(network), {'users', 'positions', 'usernames', 'colors',
                                        'communities', 'modularity', 'parameters'})
        self.assertNotIn(99, network['users'])
        communities = network['communities']
        self.assertEqual(len({communities[u] for u in group_1}), 1)
        self.assertEqual(len({communities[u] for u in group_2}), 1)
        self.assertNotEqual(communities[0], communities[10])
        self.assertGreater(network['modularity'], 0.4)
        self.assertNotIn(10, network['users'][0])


class LoaderTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def load(self, proposals, comments=None):
        call_command('load_endorses_from_csv',
                     write_csv(self.tmp.name, 'p.csv', PROPOSAL_COLUMNS, proposals), stdout=io.StringIO())
        if comments is not None:
            call_command('load_comments_from_csv',
                         write_csv(self.tmp.name, 'c.csv', COMMENT_COLUMNS, comments),
                         stdout=io.StringIO(), stderr=io.StringIO())

    def test_existing_users_endorsements_are_kept(self):
        # Regression: only a user's first endorsement used to be stored.
        self.load([proposal_row(1, 'Ana, Bob'), proposal_row(2, 'Ana'), proposal_row(3, '')])
        ana = User.objects.get(name='Ana')
        self.assertEqual(set(ana.proposal_set.values_list('id_proposal', flat=True)), {1, 2})
        self.assertEqual(Proposal.objects.get(id_proposal=1).endorsements, 2)

    def test_empty_endorsements_count_as_zero(self):
        self.load([proposal_row(3, '')])
        self.assertEqual(Proposal.objects.get(id_proposal=3).endorsements, 0)

    def test_categories_and_blank_coordinates(self):
        self.load([proposal_row(1, **{'category/id': '7', 'category/name/en': 'Climate'}),
                   proposal_row(2, **{'category/id': '7'})])
        p1, p2 = Proposal.objects.order_by('id_proposal')
        self.assertEqual(p1.category_id, 7)
        self.assertEqual(p2.category_id, 7)
        self.assertIsNone(p1.latitude)

    def test_reloading_is_idempotent(self):
        rows = [proposal_row(1, 'Ana, Bob')]
        self.load(rows)
        self.load(rows)
        self.assertEqual(Proposal.objects.count(), 1)
        self.assertEqual(User.objects.count(), 2)

    def test_comments_and_replies_attach_to_the_right_proposal(self):
        comments = [
            # Reply listed before its parent, and before a comment on another proposal.
            {'id': 11, 'depth': 1, 'author/name': 'Bob', 'commentable_id': 10, 'root_commentable_id': 1,
             'created_at': '2022-01-03 10:00:00 UTC', 'locale': 'en'},
            {'id': 20, 'depth': 0, 'author/name': 'Cat', 'commentable_id': 2, 'root_commentable_id': 2,
             'created_at': '2022-01-02 10:00:00 UTC', 'locale': 'es'},
            {'id': 10, 'depth': 0, 'author/name': 'Ana', 'commentable_id': 1, 'root_commentable_id': 1,
             'created_at': '2022-01-02 09:00:00 UTC', 'locale': 'en'},
            {'id': 30, 'depth': 0, 'author/name': 'Dan', 'commentable_id': 999, 'root_commentable_id': 999,
             'created_at': '2022-01-02 09:00:00 UTC', 'locale': 'en'},  # unknown proposal -> skipped
        ]
        self.load([proposal_row(1), proposal_row(2)], comments)

        reply = Comment.objects.get(id_comment=11)
        self.assertEqual(reply.proposal_replied_id, 1)
        self.assertEqual(reply.reply_to_id, 10)
        self.assertEqual(set(Proposal.objects.get(id_proposal=1).comments.values_list('id_comment', flat=True)),
                         {10, 11})
        self.assertFalse(Comment.objects.filter(id_comment=30).exists())


class ViewTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        settings_override = override_settings(DECIDIM_VIZ_CACHE_DIR=self.tmp.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        users = [User.objects.create(name=name) for name in ('Ana', 'Bob', 'Cat')]
        self.p1, self.p2, self.p3 = [Proposal.objects.create(id_proposal=i, proposal_title_es='',
                                                             proposal_title_en='P{}'.format(i),
                                                             proposal_title_fr='') for i in (1, 2, 3)]
        self.p2.users.add(*users)
        self.p1.users.add(users[0])
        for i, user in enumerate(users):
            Comment.objects.create(id_comment=100 + i, author=user, proposal_replied=self.p3)

    def test_most_commented_and_most_endorsed(self):
        # Regression: both used to return the *least* commented/endorsed proposal.
        self.assertEqual(self.client.get('/stats/proposals/comments/first').json()['id'], 3)
        self.assertEqual(self.client.get('/stats/proposals/endorses/first').json()['id'], 2)

    def test_network_endpoints_compute_and_cache(self):
        for url, cache_file in (('/stats/comments/', 'comments_all.pickle'),
                                ('/stats/endorsements/', 'endorsement_all.pickle')):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('modularity', response.json())
            self.assertTrue(os.path.exists(os.path.join(self.tmp.name, cache_file)))

    def test_modularity_endpoints(self):
        for kind in ('comments', 'endorsements'):
            response = self.client.get('/stats/{}/modularity'.format(kind))  # no trailing slash, as the front end calls it
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.json()), {'modularity'})
            network = self.client.get('/stats/{}/'.format(kind)).json()
            self.assertEqual(response.json()['modularity'], network['modularity'])

    def test_modularity_endpoint_reads_the_cache(self):
        call_command('generate_endorses_cache', '--alpha', '1', '--correction', 'none', stdout=io.StringIO())
        with open(os.path.join(self.tmp.name, 'endorsement_all.pickle'), 'rb') as handle:
            cached = pickle.load(handle)
        cached['modularity'] = 0.123  # a value only the cache can provide
        with open(os.path.join(self.tmp.name, 'endorsement_all.pickle'), 'wb') as handle:
            pickle.dump(cached, handle)
        self.assertEqual(self.client.get('/stats/endorsements/modularity').json(), {'modularity': 0.123})

    def test_cache_commands(self):
        out = io.StringIO()
        call_command('generate_endorses_cache', '--alpha', '1', '--correction', 'none', stdout=out)
        self.assertIn('endorsements network: 3 users', out.getvalue())
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, 'endorsement_all.pickle')))


class DistinctColorsTests(TestCase):
    def test_colors_are_unique_beyond_the_old_period(self):
        # The old formula repeated every 255 communities, which would merge them as API keys.
        colors = distinct_colors(5000)
        self.assertEqual(len(set(colors)), 5000)
        self.assertTrue(all(0 <= c <= 255 for rgb in colors for c in rgb))

    def test_hex(self):
        self.assertEqual(to_hex((255, 0, 16)), '#ff0010')


class ColorsEndpointTests(TestCase):
    """Two groups of five users, each endorsing its own five proposals."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        settings_override = override_settings(DECIDIM_VIZ_CACHE_DIR=self.tmp.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        proposals = {i: Proposal.objects.create(id_proposal=i, proposal_title_en='EN {}'.format(i),
                                                proposal_title_es='ES {}'.format(i), proposal_title_fr='')
                     for i in range(1, 21)}
        self.groups = []
        for g, proposal_ids in enumerate((range(1, 6), range(6, 11))):
            users = [User.objects.create(name='g{}u{}'.format(g, k)) for k in range(5)]
            for i in proposal_ids:
                proposals[i].users.add(*users)
            self.groups.append(({u.id for u in users}, set(proposal_ids)))

    def test_shape_and_communities(self):
        response = self.client.get('/stats/endorsements/colors')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['total'], 10)
        users, proposals = data['colors']['users'], data['colors']['proposals']
        self.assertEqual(len(users), 2)
        self.assertEqual(set(users), set(proposals))
        self.assertTrue(all(color.startswith('#') and len(color) == 7 for color in users))

        for color, members in users.items():
            members = set(members)
            group_proposals = next(props for ids, props in self.groups if ids == members)
            self.assertEqual(len(proposals[color]), 3)
            for title, count in proposals[color].items():
                self.assertIn(int(title.split()[1]), group_proposals)
                self.assertEqual(count, 5)

    def test_colors_match_the_network(self):
        data = self.client.get('/stats/endorsements/colors').json()
        network = self.client.get('/stats/endorsements/').json()
        for color, members in data['colors']['users'].items():
            for user in members:
                self.assertEqual(to_hex(network['colors'][str(user)]), color)

    def test_parameters(self):
        data = self.client.get('/stats/endorsements/colors?proposals=1&lang=es').json()
        for top in data['colors']['proposals'].values():
            self.assertEqual(len(top), 1)
            self.assertTrue(next(iter(top)).startswith('ES '))
        self.assertEqual(self.client.get('/stats/endorsements/colors?proposals=x').status_code, 400)
        self.assertEqual(self.client.get('/stats/endorsements/colors?proposals=-1').status_code, 400)

    def test_language_falls_back_when_title_missing(self):
        data = self.client.get('/stats/endorsements/colors?lang=fr').json()
        titles = [title for top in data['colors']['proposals'].values() for title in top]
        self.assertTrue(all(title.startswith('EN ') for title in titles))

    def test_comments_colors(self):
        response = self.client.get('/stats/comments/colors')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'total': 0, 'colors': {'users': {}, 'proposals': {}}})


def comment_row(id_, author_id, name, proposal, depth=0, parent=None):
    return {'id': id_, 'depth': depth, 'author/id': author_id, 'author/name': name,
            'commentable_id': parent if depth else proposal, 'root_commentable_id': proposal,
            'created_at': '2022-01-02 10:00:00 UTC', 'locale': 'en'}


class UserMatchingTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def load_proposals(self, rows):
        call_command('load_endorses_from_csv',
                     write_csv(self.tmp.name, 'p.csv', PROPOSAL_COLUMNS, rows), stdout=io.StringIO())

    def load_comments(self, rows):
        out = io.StringIO()
        call_command('load_comments_from_csv', write_csv(self.tmp.name, 'c.csv', COMMENT_COLUMNS, rows),
                     stdout=out, stderr=io.StringIO())
        return out.getvalue()

    def test_homonym_commenters_stay_separate(self):
        self.load_proposals([proposal_row(1), proposal_row(2)])
        self.load_comments([comment_row(10, 501, 'Maria', 1), comment_row(11, 502, 'Maria', 2)])
        marias = User.objects.filter(name='Maria')
        self.assertEqual(sorted(marias.values_list('decidim_id', flat=True)), [501, 502])
        self.assertEqual(Comment.objects.get(id_comment=11).author.decidim_id, 502)

    def test_endorser_merged_into_the_only_commenter_with_that_name(self):
        self.load_proposals([proposal_row(1, 'Ana'), proposal_row(2, 'Ana'), proposal_row(3)])
        output = self.load_comments([comment_row(10, 7, 'Ana', 3)])

        ana = User.objects.get(name='Ana')  # a single record left
        self.assertEqual(ana.decidim_id, 7)
        self.assertFalse(ana.ambiguous)
        self.assertEqual(set(ana.proposal_set.values_list('id_proposal', flat=True)), {1, 2})
        self.assertEqual(ana.comment_set.count(), 1)
        self.assertIn('1 identified by Decidim id, 0 matched by name only, 0 ambiguous', output)

    def test_endorser_name_shared_by_two_commenters_is_ambiguous(self):
        self.load_proposals([proposal_row(1, 'Maria'), proposal_row(2), proposal_row(3)])
        self.load_comments([comment_row(10, 501, 'Maria', 2), comment_row(11, 502, 'Maria', 3)])

        placeholder = User.objects.get(name='Maria', decidim_id__isnull=True)
        self.assertTrue(placeholder.ambiguous)
        self.assertEqual(list(placeholder.proposal_set.values_list('id_proposal', flat=True)), [1])
        for decidim_id in (501, 502):  # the endorsement is not given to either Maria
            self.assertFalse(User.objects.get(decidim_id=decidim_id).proposal_set.exists())

    def test_same_name_twice_on_one_proposal_is_ambiguous(self):
        self.load_proposals([proposal_row(1, 'Joan, Joan, Pau')])
        self.assertTrue(User.objects.get(name='Joan').ambiguous)
        self.assertFalse(User.objects.get(name='Pau').ambiguous)
        self.assertEqual(Proposal.objects.get(id_proposal=1).endorsements, 3)
        # An ambiguous name is not merged into a commenter even if only one has it.
        self.load_comments([comment_row(10, 9, 'Joan', 1)])
        self.assertEqual(User.objects.filter(name='Joan').count(), 2)

    def test_endorsements_reloaded_after_comments_go_to_the_identified_user(self):
        self.load_proposals([proposal_row(1)])
        self.load_comments([comment_row(10, 7, 'Ana', 1)])
        self.load_proposals([proposal_row(1), proposal_row(2, 'Ana')])
        self.assertEqual(User.objects.filter(name='Ana').count(), 1)
        self.assertEqual(list(User.objects.get(decidim_id=7).proposal_set.values_list('id_proposal', flat=True)), [2])

    def test_reloading_is_idempotent(self):
        proposals = [proposal_row(1, 'Ana, Bob')]
        comments = [comment_row(10, 7, 'Ana', 1), comment_row(11, 8, 'Cat', 1)]
        for _ in range(2):
            self.load_proposals(proposals)
            self.load_comments(comments)
        self.assertEqual(sorted(User.objects.values_list('name', flat=True)), ['Ana', 'Bob', 'Cat'])

    def test_renamed_commenter_keeps_one_record(self):
        self.load_proposals([proposal_row(1)])
        self.load_comments([comment_row(10, 7, 'Ana', 1)])
        self.load_comments([comment_row(10, 7, 'Ana Puig', 1)])
        self.assertEqual(list(User.objects.values_list('decidim_id', 'name')), [(7, 'Ana Puig')])

    def test_comments_without_author_go_to_one_ambiguous_record(self):
        self.load_proposals([proposal_row(1)])
        self.load_comments([comment_row(10, '', '', 1), comment_row(11, '', '', 1)])
        unknown = User.objects.get()
        self.assertTrue(unknown.ambiguous)
        self.assertEqual(unknown.comment_set.count(), 2)

    def test_ambiguous_users_are_left_out_of_the_networks(self):
        from stats.networks import comment_memberships, compute_network, endorsement_memberships
        self.load_proposals([proposal_row(1, 'Joan, Joan, Pau'), proposal_row(2)])
        self.load_comments([comment_row(10, '', '', 2), comment_row(11, 3, 'Pau', 2)])
        joan, unknown = User.objects.get(name='Joan'), User.objects.get(name='[unknown author]')
        self.assertNotIn(joan.id, endorsement_memberships())
        self.assertNotIn(unknown.id, comment_memberships())
        self.assertIn(User.objects.get(name='Pau').id, comment_memberships())
        self.assertEqual(compute_network('endorsements')['parameters']['n_ambiguous_users_excluded'], 2)


class ReplyLinkTests(TestCase):
    def test_replies_point_one_way(self):
        # Regression: a symmetrical ManyToManyField('self') listed the parent among its reply's "comments".
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        call_command('load_endorses_from_csv', write_csv(tmp.name, 'p.csv', PROPOSAL_COLUMNS, [proposal_row(1)]),
                     stdout=io.StringIO())
        rows = [comment_row(10, 1, 'Ana', 1), comment_row(11, 2, 'Bob', 1, depth=1, parent=10),
                comment_row(12, 3, 'Cat', 1, depth=2, parent=11)]
        call_command('load_comments_from_csv', write_csv(tmp.name, 'c.csv', COMMENT_COLUMNS, rows),
                     stdout=io.StringIO(), stderr=io.StringIO())

        top, reply, nested = (Comment.objects.get(id_comment=i) for i in (10, 11, 12))
        self.assertEqual(list(top.replies.values_list('id_comment', flat=True)), [11])
        self.assertEqual(list(reply.replies.values_list('id_comment', flat=True)), [12])
        self.assertFalse(nested.replies.exists())
        self.assertIsNone(top.reply_to)
        self.assertEqual(nested.reply_to, reply)


class NewerExportFormatTests(TestCase):
    """Decidim >= 0.28 exports: likes instead of endorsements, title/<lang>, taxonomies, +hhmm offsets."""

    def test_load_newer_proposals_export(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        columns = ['id', 'title/ca', 'title/en', 'title/machine_translations/es', 'published_at',
                   'likes/total_count', 'likes/user_likes', 'taxonomies/ids',
                   'taxonomies/1085/en', 'taxonomies/1085/es', 'taxonomies/1088/en', 'latitude', 'longitude']
        rows = [{'id': 1, 'title/ca': 'Hola', 'title/en': 'Hello', 'title/machine_translations/es': 'Hola (MT)',
                 'published_at': '2017-10-06 10:48:14 +0200', 'likes/total_count': 2,
                 'likes/user_likes': 'Ana, Bob', 'taxonomies/ids': '1085, 1088',
                 'taxonomies/1085/en': 'Governance', 'taxonomies/1085/es': 'Gobernanza',
                 'taxonomies/1088/en': 'Other'}]
        call_command('load_endorses_from_csv', write_csv(tmp.name, 'p.csv', columns, rows), stdout=io.StringIO())

        proposal = Proposal.objects.get(id_proposal=1)
        self.assertEqual((proposal.proposal_title_en, proposal.proposal_title_es, proposal.proposal_title_fr),
                         ('Hello', 'Hola (MT)', ''))
        self.assertEqual(proposal.endorsements, 2)
        self.assertEqual(set(proposal.users.values_list('name', flat=True)), {'Ana', 'Bob'})
        self.assertEqual(proposal.published_at,  # stored in UTC; same instant
                         datetime(2017, 10, 6, 8, 48, 14, tzinfo=timezone.utc))
        self.assertEqual((proposal.category_id, proposal.category.name_en, proposal.category.name_es),
                         (1085, 'Governance', 'Gobernanza'))


class LayoutTests(TestCase):
    def test_spring_layout_for_connected_users_and_ring_for_isolated(self):
        from stats.phi.phi import network_layout
        import networkx as nx
        graph = nx.Graph()
        graph.add_weighted_edges_from([(1, 2, 0.9), (2, 3, 0.8), (1, 3, 0.7), (4, 5, 0.6)], weight='phi')
        graph.add_nodes_from([6, 7])
        positions, layout = network_layout(graph, [{1, 2, 3}, {4, 5}, {6}, {7}], seed=1)

        self.assertEqual(layout, 'spring')
        self.assertEqual(set(positions), {1, 2, 3, 4, 5, 6, 7})
        radius = lambda node: (positions[node][0] ** 2 + positions[node][1] ** 2) ** 0.5
        for node in (1, 2, 3, 4, 5):
            self.assertLessEqual(radius(node), 1.0 + 1e-9)
        for node in (6, 7):
            self.assertAlmostEqual(radius(node), 1.25)
        # Same seed, same picture.
        self.assertEqual(network_layout(graph, [{1, 2, 3}, {4, 5}, {6}, {7}], seed=1)[0], positions)

    def test_large_or_edgeless_networks_fall_back_to_a_circle(self):
        from stats.phi import phi
        import networkx as nx
        edgeless = nx.Graph()
        edgeless.add_nodes_from([1, 2, 3])
        self.assertEqual(phi.network_layout(edgeless, [{1}, {2}, {3}])[1], 'circular')

        big = nx.path_graph(12)
        nx.set_edge_attributes(big, 0.5, 'phi')
        original = phi.MAX_SPRING_LAYOUT_NODES
        phi.MAX_SPRING_LAYOUT_NODES = 10
        self.addCleanup(setattr, phi, 'MAX_SPRING_LAYOUT_NODES', original)
        positions, layout = phi.network_layout(big, [set(range(12))])
        self.assertEqual(layout, 'circular')
        self.assertEqual(len(positions), 12)


class GiniTests(TestCase):
    def test_known_value_and_contributions(self):
        from stats.statistics import gini
        value, contributions = gini([0, 0, 0, 1])
        self.assertAlmostEqual(value, 0.75)
        self.assertEqual([round(c, 6) for c in contributions], [0.125, 0.125, 0.125, 0.375])

    def test_matches_the_definition(self):
        from stats.statistics import gini
        rng = np.random.default_rng(3)
        x = rng.integers(0, 20, size=37).astype(float)
        n, mean = len(x), x.mean()
        expected = [np.abs(xi - x).sum() / (2 * n * n * mean) for xi in x]
        value, contributions = gini(x)
        np.testing.assert_allclose(contributions, expected)
        self.assertAlmostEqual(value, sum(expected))

    def test_degenerate_inputs(self):
        from stats.statistics import gini
        self.assertEqual(gini([]), (0.0, []))
        self.assertEqual(gini([0, 0]), (0.0, [0.0, 0.0]))
        self.assertEqual(gini([5, 5, 5])[0], 0.0)


class StatisticsEndpointTests(TestCase):
    """Proposals 1-3; Ana comments twice on 1 and endorses 2; Bob comments once
    on 1 (a reply); Cat only endorses; Dan does nothing; an ambiguous record
    comments on 3."""

    def setUp(self):
        utc = timezone.utc
        self.ana, self.bob, self.cat, self.dan = (User.objects.create(name=n, decidim_id=i)
                                                 for i, n in enumerate(('Ana', 'Bob', 'Cat', 'Dan'), 1))
        ghost = User.objects.create(name='[unknown author]', ambiguous=True)
        p1, p2, p3 = (Proposal.objects.create(id_proposal=i, proposal_title_en='P{}'.format(i),
                                              proposal_title_es='', proposal_title_fr='',
                                              published_at=datetime(2022, 1, i, 10, tzinfo=utc),
                                              endorsements=e)
                      for i, e in ((1, 0), (2, 2), (3, 0)))
        p2.users.add(self.ana, self.cat)
        c10 = Comment.objects.create(id_comment=10, author=self.ana, proposal_replied=p1, body_length=40,
                                     created_at=datetime(2022, 1, 1, 13, tzinfo=utc))
        Comment.objects.create(id_comment=11, author=self.bob, proposal_replied=p1, depth=1, reply_to=c10,
                               body_length=5, created_at=datetime(2022, 1, 2, 10, tzinfo=utc))
        Comment.objects.create(id_comment=12, author=self.ana, proposal_replied=p1, body_length=None,
                               created_at=datetime(2022, 1, 5, 10, tzinfo=utc))
        Comment.objects.create(id_comment=13, author=ghost, proposal_replied=p3, body_length=7,
                               created_at=datetime(2022, 1, 2, 10, tzinfo=utc))  # 23h before p3 was published

    def get(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return response.json()

    def test_dates(self):
        self.assertEqual(self.get('/stats/dates'), {
            'proposals_from': '2022-01-01T10:00:00+00:00', 'proposals_to': '2022-01-03T10:00:00+00:00',
            'comments_from': '2022-01-01T13:00:00+00:00', 'comments_to': '2022-01-05T10:00:00+00:00'})

    def test_summary(self):
        # Ana and Bob comment, Ana and Cat endorse; Dan and the ambiguous record do not count.
        self.assertEqual(self.get('/stats/summary'), {'participants': 3, 'proposals': 3, 'comments': 4})

    def test_participation_types_exclude_ambiguous_records(self):
        self.assertEqual(self.get('/stats/users/active_proportion'),
                         {'comments': 1, 'endorsements': 1, 'all': 1, 'inactive': 1})  # Bob, Cat, Ana, Dan

    def test_users_by_comments(self):
        data = self.get('/stats/users/by_comments/1')
        self.assertEqual(data['comments'], [{'id': str(self.ana.id), 'name': 'Ana', 'comments': 2}])
        # Population: Ana 2, Bob 1 -> G = 2 * 1 / (2 * 4 * 1.5)
        self.assertAlmostEqual(data['gini']['value'], 1 / 6)
        self.assertEqual(len(data['gini']['contributions']), 1)

    def test_box_data(self):
        self.assertEqual(sorted(self.get('/stats/comments/length')['box_data']), [5, 7, 40])
        self.assertEqual(sorted(self.get('/stats/comments/depth')['box_data']), [0, 0, 0, 1])
        self.assertEqual(sorted(self.get('/stats/comments/per_user')['box_data']), [1, 2])
        # p1: published 10:00, first comment 13:00; p3's comment predates it and is left out.
        self.assertEqual(self.get('/stats/proposals/responses/first/time/')['box_data'], [3.0])

    def test_proposals_with_and_without_comments(self):
        self.assertEqual(self.get('/stats/proposals/responses/comments/count'), {'0': 1, '>0': 2})

    def test_rankings_include_gini(self):
        data = self.get('/stats/proposals/supports/2')
        self.assertAlmostEqual(data['gini']['value'], 2 / 3)  # endorsements 0, 2, 0
        self.assertEqual(len(data['gini']['contributions']), 2)
        self.assertIn('gini', self.get('/stats/proposals/comments/2'))
        self.assertIn('gini', self.get('/stats/categories/proposals/2'))
        self.assertIn('gini', self.get('/stats/categories/comments/'))

    def test_comment_length_is_imported(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        columns = COMMENT_COLUMNS + ['body']
        rows = [dict(comment_row(20, 1, 'Ana', 1), body='Hola, món')]
        call_command('load_comments_from_csv', write_csv(tmp.name, 'c.csv', columns, rows),
                     stdout=io.StringIO(), stderr=io.StringIO())
        self.assertEqual(Comment.objects.get(id_comment=20).body_length, 9)


class ProposalTitleAndLinkTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        columns = ['id', 'title/ca', 'title/en', 'title/es', 'published_at', 'likes/user_likes',
                   'url', 'participatory_space/url']
        rows = [
            {'id': 1, 'title/ca': 'Només en català', 'published_at': '2020-01-01 10:00:00 +0100',
             'likes/user_likes': 'Ana, Bob',
             'url': 'https://example.org/processes/p/f/1/proposals/1',
             'participatory_space/url': 'https://example.org/processes/p'},
            {'id': 2, 'title/en': 'In English', 'title/es': 'En castellano', 'published_at': '2020-01-01 10:00:00 +0100',
             'likes/user_likes': 'Ana', 'participatory_space/url': 'https://example.org/processes/q'},
        ]
        call_command('load_endorses_from_csv', write_csv(tmp.name, 'p.csv', columns, rows), stdout=io.StringIO())

    def test_links_point_to_the_proposal_not_the_process(self):
        self.assertEqual(Proposal.objects.get(id_proposal=1).url, 'https://example.org/processes/p/f/1/proposals/1')
        # Exports without a proposal URL still give the space's.
        self.assertEqual(Proposal.objects.get(id_proposal=2).url, 'https://example.org/processes/q')

    def test_every_proposal_has_a_title(self):
        data = self.client.get('/stats/proposals/supports/2').json()['proposals']
        self.assertEqual([(p['id'], p['title'], p['title_es']) for p in data],
                         [(1, 'Només en català', ''), (2, 'In English', 'En castellano')])
        self.assertEqual(self.client.get('/stats/proposal/1').json()['title'], 'Només en català')
        self.assertEqual(Proposal(id_proposal=9).display_title, '#9')


class NodeOverlapTests(TestCase):
    def assert_no_overlaps(self, positions, d):
        from scipy.spatial import cKDTree
        xy = np.array(list(positions.values()))
        self.assertEqual(len(cKDTree(xy).query_pairs(d * (1 - 1e-6))), 0)
        self.assertLessEqual(np.linalg.norm(xy, axis=1).max(), 1 + 1e-9)

    def test_clustered_nodes_are_spread_out(self):
        from stats.phi.phi import MIN_NODE_DISTANCE, remove_overlaps
        rng = np.random.default_rng(0)
        positions = {i: (rng.normal(0, 0.01, 2) + [0.3, 0.2]).tolist() for i in range(60)}
        self.assert_no_overlaps(remove_overlaps(positions), MIN_NODE_DISTANCE)

    def test_separated_nodes_do_not_move(self):
        from stats.phi.phi import remove_overlaps
        positions = {'a': [0.0, 0.0], 'b': [0.5, 0.0], 'c': [0.0, -0.5]}
        self.assertEqual(remove_overlaps(positions), positions)

    def test_identical_positions_are_separated(self):
        from stats.phi.phi import MIN_NODE_DISTANCE, remove_overlaps
        self.assert_no_overlaps(remove_overlaps({i: [0.1, 0.1] for i in range(5)}), MIN_NODE_DISTANCE)

    def test_dense_layouts_still_fit_in_the_disc(self):
        from stats.phi.phi import min_node_distance, remove_overlaps
        rng = np.random.default_rng(1)
        angle, radius = rng.uniform(0, 2 * np.pi, 3000), np.sqrt(rng.uniform(0, 1, 3000))
        positions = {i: [r * np.cos(a), r * np.sin(a)] for i, (a, r) in enumerate(zip(angle, radius))}
        d = min_node_distance(3000)
        self.assertLess(d, 0.06)  # spacing reduced so that 3000 nodes fit
        self.assert_no_overlaps(remove_overlaps(positions), d)

    def test_layout_of_a_real_network_has_no_overlaps(self):
        # Regression: on meta.decidim.org's endorsements network, 26 pairs of drawn nodes overlapped.
        from stats.phi.phi import MIN_NODE_DISTANCE, network_layout
        import networkx as nx
        graph = nx.complete_graph(30)  # a dense clique: the spring layout bunches it up
        graph.add_edges_from((i, i + 1) for i in range(30, 60))
        nx.set_edge_attributes(graph, 0.9, 'phi')
        positions, layout = network_layout(graph, [set(range(30)), set(range(30, 61))], seed=3)
        self.assertEqual(layout, 'spring')
        self.assert_no_overlaps(positions, MIN_NODE_DISTANCE)


class InstanceEndpointTests(TestCase):
    def create(self, id_, url):
        Proposal.objects.create(id_proposal=id_, proposal_title_es='', proposal_title_en='', proposal_title_fr='', url=url)

    def test_reports_the_instance_of_the_proposals(self):
        self.create(1, 'https://meta.decidim.org/en/processes/roadmap/f/122/proposals/1')
        self.create(2, 'https://meta.decidim.org/en/processes/roadmap/f/122/proposals/2')
        self.create(3, 'https://other.example.org/processes/x/f/1/proposals/3')
        self.create(4, None)
        data = self.client.get('/stats/instance').json()
        self.assertEqual(data['name'], 'meta.decidim.org')
        self.assertEqual(data['url'], 'https://meta.decidim.org')
        self.assertEqual(data['api_url'], 'https://meta.decidim.org/api')
        self.assertEqual(data['hosts'], [{'name': 'meta.decidim.org', 'proposals': 2},
                                         {'name': 'other.example.org', 'proposals': 1}])

    def test_empty_database(self):
        self.assertEqual(self.client.get('/stats/instance').json(), {'name': None, 'url': None, 'api_url': None, 'hosts': []})
