from diskcache import Cache as diskCache
#from cachetools import TTLCache

class Cache():

    def __init__(self, dir: str, expires: int = None):
        self.cache = diskCache(dir)
        self.expires = expires

    def set(self, key, value):
        self.cache.set(key, value, expire=self.expires)

    def get(self, key, default=None):
        return self.cache.get(key, default)
    
    def clear(self):
        return self.cache.clear()

    def expire(self):
        return self.cache.expire()
    
    def close(self):
        return self.cache.close()
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
