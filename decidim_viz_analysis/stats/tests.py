import csv
import io
import os
import pickle
import tempfile

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
