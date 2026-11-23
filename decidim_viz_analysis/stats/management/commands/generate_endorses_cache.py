from stats.management.network_cache_command import NetworkCacheCommand


class Command(NetworkCacheCommand):
    help = 'Compute the phi network of users who endorse the same proposals and cache it.'
    kind = 'endorsements'
