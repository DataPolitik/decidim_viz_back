from django.core.management.base import BaseCommand

from stats.networks import cache_path, compute_network, write_cache
from stats.phi.phi import CORRECTIONS, DEFAULT_ALPHA, DEFAULT_CORRECTION, DEFAULT_SEED


class NetworkCacheCommand(BaseCommand):
    """Shared implementation of generate_comments_cache and generate_endorses_cache."""
    kind = None

    def add_arguments(self, parser):
        parser.add_argument('output_path', nargs='?', default=None,
                            help='Where to write the pickle (default: the cache file the API reads).')
        parser.add_argument('--alpha', type=float, default=DEFAULT_ALPHA,
                            help='Significance level of the hypergeometric test (default: %(default)s).')
        parser.add_argument('--correction', choices=CORRECTIONS, default=DEFAULT_CORRECTION,
                            help='Multiple-testing correction over all user pairs: Benjamini-Hochberg '
                                 'false discovery rate, Bonferroni, or none (default: %(default)s).')
        parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                            help='Random seed for Louvain community detection (default: %(default)s).')

    def handle(self, *args, **options):
        path = options['output_path'] or cache_path(self.kind)
        network = compute_network(self.kind, alpha=options['alpha'], correction=options['correction'],
                                  seed=options['seed'])
        write_cache(network, path)
        params = network['parameters']
        self.stdout.write('{} network: {} users, {} edges, {} communities, modularity {:.3f} -> {}'.format(
            self.kind, params['n_users'], params['n_edges'], len(set(network['communities'].values())),
            network['modularity'], path))
