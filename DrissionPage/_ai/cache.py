# -*- coding:utf-8 -*-
"""
In-memory cache for AI planning.
"""


class AIPlanCache(object):
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value
        return value
