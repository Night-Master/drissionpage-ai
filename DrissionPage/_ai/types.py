# -*- coding:utf-8 -*-
"""
Lightweight runtime types for DrissionPage AI.
"""


class AILocateResult(object):
    def __init__(self, prompt, element, xpath, rect_page=None, center_page=None,
                 confidence=None, reason=None, debug=None, source=None, viewport_bbox=None,
                 center_viewport=None):
        self.prompt = prompt
        self.element = element
        self.xpath = xpath
        self.rect_page = rect_page or {}
        self.center_page = center_page or {}
        self.center_viewport = center_viewport or {}
        self.confidence = confidence
        self.reason = reason
        self.debug = debug or {}
        self.source = source
        self.viewport_bbox = viewport_bbox or {}

    def as_dict(self):
        return {
            'prompt': self.prompt,
            'xpath': self.xpath,
            'rect_page': self.rect_page,
            'center_page': self.center_page,
            'center_viewport': self.center_viewport,
            'confidence': self.confidence,
            'reason': self.reason,
            'tag': getattr(self.element, 'tag', None),
            'debug': self.debug,
            'source': self.source,
            'viewport_bbox': self.viewport_bbox,
        }
