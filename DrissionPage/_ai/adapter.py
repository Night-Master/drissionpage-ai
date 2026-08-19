# -*- coding:utf-8 -*-
"""
Adapter from DrissionPage objects to AI helpers.
"""
from math import hypot
from random import uniform
from time import sleep


DOM_HELPERS_JS = r'''
    function dpAiIsVisible(el) {
        if (!el || !el.getBoundingClientRect) return false;
        const style = window.getComputedStyle(el);
        if (!style) return false;
        if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || 1) === 0) {
            return false;
        }
        const rect = el.getBoundingClientRect();
        return rect.width >= 2 && rect.height >= 2;
    }

    function dpAiIsInteractive(el) {
        if (!el || !el.tagName) return false;
        const tag = el.tagName.toLowerCase();
        if (['button', 'a', 'input', 'textarea', 'select', 'option', 'summary', 'label'].includes(tag)) {
            return true;
        }
        if (el.isContentEditable) return true;
        if (el.onclick) return true;
        const role = (el.getAttribute('role') || '').toLowerCase();
        if (role && ['button', 'link', 'tab', 'checkbox', 'radio', 'menuitem', 'switch'].includes(role)) {
            return true;
        }
        const tabindex = el.getAttribute('tabindex');
        return tabindex !== null && tabindex !== '-1';
    }

    function dpAiCleanText(text) {
        return (text || '').replace(/\s+/g, ' ').trim();
    }

    function dpAiTextFor(el) {
        let text = dpAiCleanText(el.innerText || el.textContent || '');
        if (!text && el.tagName && el.tagName.toLowerCase() === 'input') {
            text = dpAiCleanText(el.value || '');
        }
        return text.slice(0, 200);
    }

    function dpAiAttr(el, name) {
        return dpAiCleanText(el.getAttribute(name) || '').slice(0, 160);
    }

    function dpAiXpathFor(el) {
        if (!el || el.nodeType !== 1) return '';
        if (el === document.documentElement) return '/html';
        if (el === document.body) return '/html/body';
        const parts = [];
        while (el && el.nodeType === 1 && el !== document.documentElement) {
            let index = 1;
            let sibling = el.previousElementSibling;
            while (sibling) {
                if (sibling.tagName === el.tagName) index += 1;
                sibling = sibling.previousElementSibling;
            }
            parts.unshift('/' + el.tagName.toLowerCase() + '[' + index + ']');
            el = el.parentElement;
            if (el === document.body) {
                parts.unshift('/html/body');
                break;
            }
        }
        return parts.join('');
    }

    function dpAiElementInfo(el) {
        if (!dpAiIsVisible(el)) return null;
        const rect = el.getBoundingClientRect();
        return {
            tag: (el.tagName || '').toLowerCase(),
            text: dpAiTextFor(el),
            aria_label: dpAiAttr(el, 'aria-label'),
            placeholder: dpAiAttr(el, 'placeholder'),
            title: dpAiAttr(el, 'title'),
            alt: dpAiAttr(el, 'alt'),
            value: dpAiCleanText((el.value || '')).slice(0, 120),
            type: dpAiAttr(el, 'type'),
            role: dpAiAttr(el, 'role'),
            name: dpAiAttr(el, 'name'),
            id: dpAiAttr(el, 'id'),
            class_name: dpAiAttr(el, 'class'),
            href: dpAiAttr(el, 'href'),
            interactive: dpAiIsInteractive(el),
            xpath: dpAiXpathFor(el),
            rect_page: {
                left: Math.round(rect.left + window.scrollX),
                top: Math.round(rect.top + window.scrollY),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            },
            center_page: {
                x: Math.round(rect.left + window.scrollX + rect.width / 2),
                y: Math.round(rect.top + window.scrollY + rect.height / 2)
            },
            rect_viewport: {
                left: Math.round(rect.left),
                top: Math.round(rect.top),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            }
        };
    }
'''

EXTRACT_ELEMENTS_JS = DOM_HELPERS_JS + r'''
    const dpAiMaxItems = arguments[0];
    const maxItems = Number(dpAiMaxItems || 180);
    const nodes = Array.prototype.slice.call(document.querySelectorAll('body *'));
    const items = [];
    for (let i = 0; i < nodes.length; i++) {
        const item = dpAiElementInfo(nodes[i]);
        if (!item) continue;
        if (!(item.interactive || item.text || item.aria_label || item.placeholder || item.title || item.alt || item.value)) {
            continue;
        }
        items.push(item);
    }

    items.sort(function(a, b) {
        if (a.interactive !== b.interactive) return a.interactive ? -1 : 1;
        const aArea = a.rect_page.width * a.rect_page.height;
        const bArea = b.rect_page.width * b.rect_page.height;
        return bArea - aArea;
    });

    const sliced = items.slice(0, maxItems);
    for (let j = 0; j < sliced.length; j++) {
        sliced[j].index = j;
    }
    return sliced;
'''

ELEMENTS_AT_POINT_JS = DOM_HELPERS_JS + r'''
    const dpAiX = arguments[0];
    const dpAiY = arguments[1];
    const dpAiMaxItems = arguments[2];
    const maxItems = Number(dpAiMaxItems || 12);
    const nodes = document.elementsFromPoint(dpAiX, dpAiY) || [];
    const items = [];
    const seen = {};
    for (let i = 0; i < nodes.length; i++) {
        const item = dpAiElementInfo(nodes[i]);
        if (!item || !item.xpath || seen[item.xpath]) continue;
        seen[item.xpath] = true;
        item.stack_index = i;
        items.push(item);
        if (items.length >= maxItems) break;
    }
    return items;
'''


class DrissionPageAIAdapter(object):
    def __init__(self, page):
        self._page = page
        self._assert_supported()

    @property
    def page(self):
        return self._page

    @property
    def url(self):
        return self._page.url

    @property
    def title(self):
        return self._page.title

    @property
    def html(self):
        return self._page.html

    def evaluate_javascript(self, script):
        return self._page.run_js(script)

    def get_metrics(self):
        layout = self._page.run_cdp_loaded('Page.getLayoutMetrics')
        window_metrics = self._page.run_js('''return {
            dpr: window.devicePixelRatio || 1,
            clientWidth: document.documentElement.clientWidth || 0,
            clientHeight: document.documentElement.clientHeight || 0,
            innerWidth: window.innerWidth || 0,
            innerHeight: window.innerHeight || 0,
            scrollX: window.scrollX || window.pageXOffset || 0,
            scrollY: window.scrollY || window.pageYOffset || 0
        };''')
        visual = layout.get('visualViewport', {})
        content = layout.get('contentSize', {})
        return {
            'dpr': window_metrics.get('dpr', 1),
            'client_size': {
                'width': window_metrics.get('clientWidth', 0),
                'height': window_metrics.get('clientHeight', 0),
            },
            'viewport_size': {
                'width': visual.get('clientWidth', window_metrics.get('clientWidth', 0)),
                'height': visual.get('clientHeight', window_metrics.get('clientHeight', 0)),
            },
            'inner_size': {
                'width': window_metrics.get('innerWidth', 0),
                'height': window_metrics.get('innerHeight', 0),
            },
            'page_size': {
                'width': content.get('width', 0),
                'height': content.get('height', 0),
            },
            'scroll_position': {
                'x': visual.get('pageX', window_metrics.get('scrollX', 0)),
                'y': visual.get('pageY', window_metrics.get('scrollY', 0)),
            },
            'layout_metrics': layout,
        }

    def screenshot_base64(self, full_page=False):
        return self._page.get_screenshot(as_base64='png', full_page=full_page)

    def extract_elements(self, max_items=180):
        return self._page.run_js(EXTRACT_ELEMENTS_JS, max_items) or []

    def locate_by_xpath(self, xpath, timeout=0):
        if not xpath:
            return None
        ele = self._page._ele('xpath:{}'.format(xpath), timeout=timeout, raise_err=False, method='aiLocate()')
        if getattr(ele, '_type', None) == 'ChromiumElement':
            return ele
        return None

    def element_at_page_point(self, page_x, page_y):
        viewport_point = self.page_to_viewport_point(page_x, page_y)
        items = self.elements_at_viewport_point(viewport_point['x'], viewport_point['y'], max_items=1)
        if items:
            xpath = items[0].get('xpath')
            return self.locate_by_xpath(xpath), items[0]
        return None, None

    def viewport_to_page_point(self, x, y, metrics=None):
        metrics = metrics or self.get_metrics()
        scroll = metrics.get('scroll_position', {})
        return {
            'x': int(round((x or 0) + scroll.get('x', 0))),
            'y': int(round((y or 0) + scroll.get('y', 0))),
        }

    def page_to_viewport_point(self, x, y, metrics=None):
        metrics = metrics or self.get_metrics()
        scroll = metrics.get('scroll_position', {})
        return {
            'x': int(round((x or 0) - scroll.get('x', 0))),
            'y': int(round((y or 0) - scroll.get('y', 0))),
        }

    def elements_at_viewport_point(self, x, y, max_items=12):
        return self._page.run_js(ELEMENTS_AT_POINT_JS, int(round(x)), int(round(y)), max_items) or []

    def elements_containing_page_point(self, elements, page_x, page_y):
        matched = []
        for item in elements or []:
            rect = item.get('rect_page') or {}
            left = rect.get('left', 0)
            top = rect.get('top', 0)
            right = left + rect.get('width', 0)
            bottom = top + rect.get('height', 0)
            if left <= page_x <= right and top <= page_y <= bottom:
                matched.append(item)
        matched.sort(key=lambda i: (
            0 if i.get('interactive') else 1,
            (i.get('rect_page', {}).get('width', 0) * i.get('rect_page', {}).get('height', 0))
        ))
        return matched

    def click(self, element):
        element.click()
        return element

    def click_point(self, page_x, page_y):
        self._page.actions.move_to((page_x, page_y), duration=.1).click()
        return self._page

    def right_click(self, element):
        element.click.right()
        return element

    def right_click_point(self, page_x, page_y):
        self._page.actions.move_to((page_x, page_y), duration=.1).r_click()
        return self._page

    def double_click(self, element):
        element.click.multi(times=2)
        return element

    def double_click_point(self, page_x, page_y):
        self._page.actions.move_to((page_x, page_y), duration=.1).click(times=2)
        return self._page

    def hover(self, element):
        element.hover()
        return element

    def hover_point(self, page_x, page_y):
        self._page.actions.move_to((page_x, page_y), duration=.1)
        return self._page

    def drag_points(self, from_page_xy, to_page_xy, steps=25, duration=.6, path='curve', curve_ratio=.2):
        """Drag from one page point to another via CDP Input.dispatchMouseEvent.

        path: 'linear' for a straight slide, 'curve' for a quadratic-bezier arc
        (control point offset perpendicular to the line, random direction).
        Returns the viewport trajectory actually used, for debugging/annotation.
        """
        metrics = self.get_metrics()
        start = self.page_to_viewport_point(from_page_xy[0], from_page_xy[1], metrics=metrics)
        end = self.page_to_viewport_point(to_page_xy[0], to_page_xy[1], metrics=metrics)
        sx, sy = start['x'], start['y']
        tx, ty = end['x'], end['y']
        waypoints = [(sx, sy)] + _drag_waypoints((sx, sy), (tx, ty), steps=steps, path=path,
                                                 curve_ratio=curve_ratio)
        self._page.run_cdp_loaded('Input.dispatchMouseEvent', type='mouseMoved',
                                  x=sx, y=sy, button='none', buttons=0)
        self._page.run_cdp_loaded('Input.dispatchMouseEvent', type='mousePressed',
                                  x=sx, y=sy, button='left', buttons=1, clickCount=1)
        sleep(.05)
        interval = float(duration) / max(1, int(steps))
        for x, y in waypoints[1:]:
            self._page.run_cdp_loaded('Input.dispatchMouseEvent', type='mouseMoved',
                                      x=x, y=y, button='left', buttons=1)
            sleep(interval)
        self._page.run_cdp_loaded('Input.dispatchMouseEvent', type='mouseReleased',
                                  x=tx, y=ty, button='left', buttons=0, clickCount=1)
        return {'start_viewport': (sx, sy), 'end_viewport': (tx, ty), 'waypoints': waypoints}

    def input(self, element, value, clear=True):
        target = self.resolve_input_target(element)
        text = '' if value is None else str(value)
        self._focus_input_target(target)
        if clear:
            self._clear_input_target(target)
        if text:
            self._page.actions.type(text)

        if self._input_value_matches(target, text):
            return target

        # Fallback to DrissionPage's element input path.
        target.input(text, clear=clear)
        if self._input_value_matches(target, text):
            return target

        # Final fallback for controlled inputs or special widgets.
        self._set_input_value_by_js(target, text)
        return target

    def input_at_point(self, page_x, page_y, value, clear=True):
        target, _ = self.element_at_page_point(page_x, page_y)
        if target:
            return self.input(target, value, clear=clear)
        self.click_point(page_x, page_y)
        if clear:
            try:
                self._page.actions.key_down('CTRL').type('a').key_up('CTRL')
                self._page.actions.type('\ue017')
            except Exception:
                pass
        if value:
            self._page.actions.type(str(value))
        return None

    def keyboard_press(self, keys, element=None):
        if element:
            element.focus()
        self._page.actions.type(keys)
        return self._page

    def scroll(self, locate=None, direction='down', pixel=300, center=None):
        if locate is not None:
            self._page.scroll.to_see(locate, center=center)
            return self._page
        direction = (direction or 'down').lower()
        if direction == 'up':
            return self._page.scroll.up(pixel)
        if direction == 'left':
            return self._page.scroll.left(pixel)
        if direction == 'right':
            return self._page.scroll.right(pixel)
        if direction == 'top':
            return self._page.scroll.to_top()
        if direction == 'bottom':
            return self._page.scroll.to_bottom()
        return self._page.scroll.down(pixel)

    def resolve_input_target(self, element):
        if getattr(element, 'tag', None) in ('input', 'textarea', 'select'):
            return element
        if element.attr('contenteditable') in ('', 'true', 'plaintext-only'):
            return element

        target = element.run_js('''
        function(){
            const isEditable = (el) => {
                if (!el || !el.matches) return false;
                return el.matches('input, textarea, select, [contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"]');
            };

            if (isEditable(this)) return this;

            if (this.control && isEditable(this.control)) return this.control;

            const descendant = this.querySelector('input, textarea, select, [contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"]');
            if (descendant) return descendant;

            const label = this.closest('label');
            if (label && label.control && isEditable(label.control)) return label.control;

            if (this.labels && this.labels.length) {
                for (const labelItem of this.labels) {
                    if (labelItem && labelItem.control && isEditable(labelItem.control)) return labelItem.control;
                }
            }

            const wrapper = this.closest('[role="group"], form, section, article, div');
            if (wrapper) {
                const insideWrapper = wrapper.querySelector('input, textarea, select, [contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"]');
                if (insideWrapper) return insideWrapper;
            }

            return null;
        }
        ''')
        if getattr(target, '_type', None) == 'ChromiumElement':
            return target
        return element

    def _focus_input_target(self, target):
        try:
            target.click()
        except Exception:
            pass
        try:
            target.focus()
        except Exception:
            pass

    def _clear_input_target(self, target):
        tag = getattr(target, 'tag', None)
        if tag in ('input', 'textarea'):
            try:
                target.clear(by_js=False)
                return
            except Exception:
                pass
        if tag == 'select':
            return
        try:
            target.run_js('''
            function(){
                if (this.isContentEditable) {
                    this.innerText = '';
                    this.dispatchEvent(new Event('input', {bubbles: true}));
                    this.dispatchEvent(new Event('change', {bubbles: true}));
                }
            }
            ''')
        except Exception:
            pass

    def _input_value_matches(self, target, expected):
        tag = getattr(target, 'tag', None)
        try:
            if tag in ('input', 'textarea', 'select'):
                current = target.property('value')
            elif target.attr('contenteditable') in ('', 'true', 'plaintext-only'):
                current = target.property('innerText')
            else:
                current = target.property('value')
        except Exception:
            current = None
        current = '' if current is None else str(current)
        return current == expected

    def _set_input_value_by_js(self, target, value):
        target.run_js('''
        function(val){
            if (this.matches && this.matches('input, textarea')) {
                const setter = Object.getOwnPropertyDescriptor(this.__proto__, 'value');
                if (setter && setter.set) {
                    setter.set.call(this, val);
                } else {
                    this.value = val;
                }
                this.dispatchEvent(new Event('input', {bubbles: true}));
                this.dispatchEvent(new Event('change', {bubbles: true}));
                return;
            }
            if (this.isContentEditable) {
                this.innerText = val;
                this.dispatchEvent(new Event('input', {bubbles: true}));
                this.dispatchEvent(new Event('change', {bubbles: true}));
            }
        }
        ''', value)

    def _assert_supported(self):
        if getattr(self._page, '_type', None) == 'WebPage' and getattr(self._page, 'mode', None) == 's':
            raise RuntimeError('AI features only work in WebPage d mode.')
        if getattr(self._page, '_driver', None) is None:
            raise RuntimeError('AI features require a Chromium-based page with a running driver.')


def _drag_waypoints(from_xy, to_xy, steps=25, path='curve', curve_ratio=.2):
    """Build drag trajectory points. 'linear' interpolates the straight line;
    'curve' follows a quadratic bezier whose control point is offset perpendicular
    to the line by curve_ratio * distance, in a random direction."""
    sx, sy = from_xy
    tx, ty = to_xy
    dx, dy = tx - sx, ty - sy
    dist = hypot(dx, dy) or 1.0
    steps = max(1, int(steps))
    control = None
    if path == 'curve':
        sign = 1 if uniform(0, 1) > .5 else -1
        offset = dist * curve_ratio * sign
        control = ((sx + tx) / 2 - dy / dist * offset, (sy + ty) / 2 + dx / dist * offset)
    points = []
    for i in range(1, steps + 1):
        t = i / steps
        t = t * t * (3 - 2 * t)  # ease-in-out, avoids a robotic constant speed
        if control is not None:
            u = 1 - t
            x = u * u * sx + 2 * u * t * control[0] + t * t * tx
            y = u * u * sy + 2 * u * t * control[1] + t * t * ty
        else:
            x = sx + dx * t
            y = sy + dy * t
        points.append((x, y))
    return points
