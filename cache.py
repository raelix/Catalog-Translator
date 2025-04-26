#from diskcache import Cache
from cachetools import TTLCache

class Cache(TTLCache):

    def set(self, key, value):
        self[key] = value
