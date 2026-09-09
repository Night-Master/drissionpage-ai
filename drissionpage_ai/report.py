# -*- coding:utf-8 -*-
"""
Simple in-memory AI action report.
"""
from time import time


class AIReport(object):
    def __init__(self, adapter):
        self._adapter = adapter
        self._entries = []

    def record(self, title=None, payload=None, with_screenshot=True):
        entry = {
            'title': title or 'AI step',
            'timestamp': time(),
            'url': self._adapter.url,
            'page_title': self._adapter.title,
            'payload': payload or {},
        }
        if with_screenshot:
            entry['screenshot_base64'] = self._adapter.screenshot_base64()
        self._entries.append(entry)
        return entry

    def logs(self):
        return list(self._entries)
