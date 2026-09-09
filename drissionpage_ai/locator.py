# -*- coding:utf-8 -*-
"""
Semantic element locator.
"""
from base64 import b64decode
from io import BytesIO
from json import dump
from pathlib import Path
from re import sub
from time import strftime

from .context import build_context
from .model import _resolve_debug_dir
from .prompt_utils import parse_user_prompt, prepare_reference_images
from .types import AILocateResult


class AILocator(object):
    def __init__(self, adapter, model):
        self._adapter = adapter
        self._model = model

    def locate(self, prompt, options=None, frozen_context=None, ai_context=None):
        options = options or {}
        parsed = parse_user_prompt(prompt)
        text_prompt = parsed['text_prompt']
        reference_images = prepare_reference_images(parsed['multimodal_prompt'])
        context = build_context(self._adapter, frozen_context=frozen_context,
                                max_elements=options.get('max_elements', 180))
        self._model.last_debug = {}
        source = 'vision'

        item, reason, viewport_bbox = self._model_locate(
            text_prompt, context, ai_context, options=options, reference_images=reference_images
        )
        if item is None:
            detail = ' Reason: {}'.format(reason) if reason else ''
            raise RuntimeError('AI locate failed for "{}".{}'.format(text_prompt, detail))

        ele = self._adapter.locate_by_xpath(item.get('xpath')) if item.get('xpath') else None
        debug = self._write_debug_artifacts(prompt, item, context, reason, options, viewport_bbox=viewport_bbox)
        if self._model.last_debug:
            debug['model_request_debug'] = self._model.last_debug
        return AILocateResult(
            prompt=text_prompt,
            element=ele,
            xpath=item.get('xpath'),
            rect_page=item.get('rect_page'),
            center_page=item.get('center_page'),
            center_viewport=item.get('center_viewport'),
            confidence=item.get('confidence'),
            reason=reason,
            debug=debug,
            source=source,
            viewport_bbox=viewport_bbox,
        )

    def _model_locate(self, prompt, context, ai_context=None, options=None, reference_images=None):
        if not self._model.available:
            raise RuntimeError(
                'AI locate requires model configuration. Set OPENAI_API_KEY/BASE_URL/MODEL.'
            )
        extra_context = ai_context.strip() if isinstance(ai_context, str) else ''
        system_prompt = (
            'You locate one UI element on a webpage from a screenshot. '
            'Return the bounding box of the best-matching target in the screenshot. '
            'Return JSON only.'
        )
        user_prompt = (
            'Task: locate the target element.\n'
            'Target prompt: {prompt}\n'
            'Extra context: {extra_context}\n'
            'Page title: {title}\n'
            'Page url: {url}\n'
            'Screenshot size (css px): width={width}, height={height}\n\n'
            'Return JSON with this shape:\n'
            '{{"bbox": [x1, y1, x2, y2], "confidence": number, "reason": string, "errors": string[]}}\n'
            'Rules:\n'
            '- bbox must use screenshot CSS pixel coordinates.\n'
            '- x1,y1 is top-left and x2,y2 is bottom-right.\n'
            '- If you use normalized coordinates by mistake, keep them within 0..1000.\n'
            '- confidence must be between 0 and 1.\n'
            '- If nothing matches, return an empty bbox and explain in errors.'
        ).format(
            prompt=prompt,
            extra_context=extra_context or 'none',
            title=context['title'],
            url=context['url'],
            width=context['screenshot_size']['width'],
            height=context['screenshot_size']['height'],
        )
        model_debug = _model_debug_options(options, prompt, prefix_suffix='locate')
        result = self._model.complete_json(system_prompt, user_prompt,
                                           image_base64=context['screenshot_base64'],
                                           image_format=context['screenshot_format'],
                                           reference_images=reference_images,
                                           debug=model_debug)
        bbox_candidates = _interpret_model_bbox(result, context['screenshot_size'],
                                               model_name=getattr(self._model, 'model', ''))
        if not bbox_candidates:
            return None, result.get('reason') or _join_errors(result.get('errors')), None
        viewport_bbox = bbox_candidates[0]
        css_viewport_bbox = _scale_bbox(viewport_bbox, context.get('screenshot_model_scale'))
        center_viewport = _bbox_center(css_viewport_bbox)
        center_page = self._adapter.viewport_to_page_point(center_viewport['x'], center_viewport['y'],
                                                           metrics=context['metrics'])
        rect_page = _viewport_bbox_to_page_bbox(css_viewport_bbox, context['metrics'].get('scroll_position', {}))
        _, point_item = self._adapter.element_at_page_point(center_page['x'], center_page['y'])
        item = {
            'xpath': point_item.get('xpath') if point_item else None,
            'rect_page': rect_page,
            'center_page': center_page,
            'center_viewport': center_viewport,
            'confidence': result.get('confidence'),
        }
        if point_item:
            for key in ('text', 'aria_label', 'placeholder', 'title', 'alt', 'value', 'role', 'name', 'id',
                        'class_name', 'href', 'interactive', 'type', 'tag', 'rect_viewport'):
                item[key] = point_item.get(key)
        return item, result.get('reason'), viewport_bbox

    def _write_debug_artifacts(self, prompt, item, context, reason, options, viewport_bbox=None):
        if not options or not options.get('debug'):
            return {}

        save_dir = Path(_resolve_debug_dir(options.get('debug_dir')))
        save_dir.mkdir(parents=True, exist_ok=True)
        prefix = options.get('debug_prefix') or _safe_name(prompt) or 'ai_locate'
        timestamp = strftime('%Y%m%d_%H%M%S')
        raw_path = save_dir / '{}_{}_raw.png'.format(prefix, timestamp)
        annotated_path = save_dir / '{}_{}_annotated.png'.format(prefix, timestamp)
        meta_path = save_dir / '{}_{}_meta.json'.format(prefix, timestamp)

        image_bytes = b64decode(context['screenshot_base64'])
        with open(raw_path, 'wb') as f:
            f.write(image_bytes)

        metadata = {
            'prompt': prompt,
            'xpath': item.get('xpath'),
            'reason': reason,
            'confidence': item.get('confidence'),
            'rect_page': item.get('rect_page'),
            'center_page': item.get('center_page'),
            'viewport_bbox': viewport_bbox,
            'scroll_position': context['metrics'].get('scroll_position', {}),
            'screenshot_size': context.get('screenshot_size', {}),
            'screenshot_actual_size': context.get('screenshot_actual_size', {}),
            'screenshot_css_size': context.get('screenshot_css_size', {}),
            'screenshot_model_scale': context.get('screenshot_model_scale'),
            'screenshot_css_source': context.get('screenshot_css_source'),
        }
        with open(meta_path, 'w', encoding='utf-8') as f:
            dump(metadata, f, ensure_ascii=False, indent=2)

        debug = {
            'raw_screenshot_path': str(raw_path),
            'annotated_screenshot_path': None,
            'meta_path': str(meta_path),
        }

        try:
            from PIL import Image, ImageDraw
        except Exception:
            return debug

        image = Image.open(BytesIO(image_bytes)).convert('RGBA')
        draw = ImageDraw.Draw(image)
        css_size = context.get('screenshot_size') or {}
        scale_x = image.width / css_size.get('width', image.width)
        scale_y = image.height / css_size.get('height', image.height)

        def _scale_rect(rect):
            left, top, right, bottom = rect
            return (int(round(left * scale_x)), int(round(top * scale_y)),
                    int(round(right * scale_x)), int(round(bottom * scale_y)))

        line_width = max(2, int(round(2 * scale_x)))
        cross_r = max(4, int(round(8 * scale_x)))
        if viewport_bbox:
            draw.rectangle(_scale_rect(_bbox_to_draw_rect(viewport_bbox, context.get('screenshot_size', {}))),
                           outline=(59, 130, 246, 255), width=line_width)
        css_ref = context.get('screenshot_css_size') or css_size
        model_scale = context.get('screenshot_model_scale') or {}
        inv_x = 1.0 / (model_scale.get('x') or 1.0)
        inv_y = 1.0 / (model_scale.get('y') or 1.0)
        rect = _page_rect_to_screenshot_rect(item.get('rect_page') or {},
                                             context['metrics'].get('scroll_position', {}),
                                             css_ref)
        if rect:
            rect = (rect[0] * inv_x, rect[1] * inv_y, rect[2] * inv_x, rect[3] * inv_y)
            draw.rectangle(_scale_rect(rect), outline=(235, 64, 52, 255), width=line_width)
            cross_x, cross_y = _page_point_to_screenshot_point(item.get('center_page') or {},
                                                               context['metrics'].get('scroll_position', {}),
                                                               css_ref)
            cross_x = int(round(cross_x * inv_x * scale_x))
            cross_y = int(round(cross_y * inv_y * scale_y))
            draw.line((cross_x - cross_r, cross_y, cross_x + cross_r, cross_y), fill=(235, 64, 52, 255), width=line_width)
            draw.line((cross_x, cross_y - cross_r, cross_x, cross_y + cross_r), fill=(235, 64, 52, 255), width=line_width)
        image.save(annotated_path, format='PNG')
        debug['annotated_screenshot_path'] = str(annotated_path)
        return debug


def _norm(text):
    return sub(r'\s+', ' ', str(text or '').strip().lower())


def _safe_name(text, limit=50):
    text = _norm(text)
    text = sub(r'[^0-9a-zA-Z\u4e00-\u9fff_-]+', '_', text).strip('_')
    return text[:limit]


def _page_rect_to_screenshot_rect(rect_page, scroll_position, screenshot_size):
    if not rect_page:
        return None
    left = rect_page.get('left', 0) - scroll_position.get('x', 0)
    top = rect_page.get('top', 0) - scroll_position.get('y', 0)
    width = rect_page.get('width', 0)
    height = rect_page.get('height', 0)
    right = left + width
    bottom = top + height
    max_width = screenshot_size.get('width', right)
    max_height = screenshot_size.get('height', bottom)
    left = max(0, min(int(round(left)), int(max_width)))
    top = max(0, min(int(round(top)), int(max_height)))
    right = max(0, min(int(round(right)), int(max_width)))
    bottom = max(0, min(int(round(bottom)), int(max_height)))
    return left, top, right, bottom


def _page_point_to_screenshot_point(point_page, scroll_position, screenshot_size):
    x = point_page.get('x', 0) - scroll_position.get('x', 0)
    y = point_page.get('y', 0) - scroll_position.get('y', 0)
    max_width = screenshot_size.get('width', x)
    max_height = screenshot_size.get('height', y)
    x = max(0, min(int(round(x)), int(max_width)))
    y = max(0, min(int(round(y)), int(max_height)))
    return x, y


def _interpret_model_bbox(result, screenshot_size, model_name='', prefer_normalized=None):
    raw_bbox = result.get('bbox')
    bbox = _normalize_bbox_input(raw_bbox)
    if not bbox:
        return []
    width = screenshot_size.get('width', 0)
    height = screenshot_size.get('height', 0)
    candidates = []
    model_name = str(model_name or '').lower()
    bbox_mode = str(result.get('bbox_mode') or '').lower()
    css_valid = _looks_like_css_bbox(bbox, width, height)
    normalized_valid = _looks_like_normalized_bbox(bbox)
    if prefer_normalized is None:
        prefer_normalized = (
            bbox_mode in ('normalized', 'normalized_1000', '1000', 'gemini', 'doubao', 'qwen') or
            'doubao' in model_name or
            'qwen' in model_name or
            'gemini' in model_name or
            'ui-tars' in model_name
        )
    swapped = [bbox[1], bbox[0], bbox[3], bbox[2]]

    if prefer_normalized:
        if normalized_valid:
            candidates.append(_normalized_bbox_to_rect(bbox, width, height))
        if _looks_like_normalized_bbox(swapped) and ('gemini' in model_name or bbox_mode == 'gemini'):
            candidates.append(_normalized_bbox_to_rect(swapped, width, height))
        if css_valid:
            candidates.append(_bbox_list_to_rect(bbox))
        if _looks_like_css_bbox(swapped, width, height) and ('gemini' in model_name or bbox_mode == 'gemini'):
            candidates.append(_bbox_list_to_rect(swapped))
    else:
        if css_valid:
            candidates.append(_bbox_list_to_rect(bbox))
        if normalized_valid:
            candidates.append(_normalized_bbox_to_rect(bbox, width, height))
        if _looks_like_css_bbox(swapped, width, height) and ('gemini' in model_name or bbox_mode == 'gemini'):
            candidates.append(_bbox_list_to_rect(swapped))
        if _looks_like_normalized_bbox(swapped) and ('gemini' in model_name or bbox_mode == 'gemini'):
            candidates.append(_normalized_bbox_to_rect(swapped, width, height))

    return _dedupe_bboxes(candidates)


def _normalize_bbox_input(raw_bbox):
    if raw_bbox is None:
        return None
    if isinstance(raw_bbox, str):
        parts = [i for i in sub(r'[\[\],]+', ' ', raw_bbox).split() if i]
        if len(parts) >= 4:
            try:
                return [float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])]
            except Exception:
                return None
        return None
    if isinstance(raw_bbox, list):
        if raw_bbox and isinstance(raw_bbox[0], list):
            return _normalize_bbox_input(raw_bbox[0])
        if len(raw_bbox) >= 4:
            try:
                return [float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3])]
            except Exception:
                return None
    return None


def _looks_like_css_bbox(bbox, width, height):
    if not bbox or width <= 0 or height <= 0:
        return False
    x1, y1, x2, y2 = bbox
    return 0 <= x1 <= width and 0 <= x2 <= width and 0 <= y1 <= height and 0 <= y2 <= height and x2 > x1 and y2 > y1


def _looks_like_normalized_bbox(bbox):
    if not bbox:
        return False
    x1, y1, x2, y2 = bbox
    return 0 <= x1 <= 1000 and 0 <= x2 <= 1000 and 0 <= y1 <= 1000 and 0 <= y2 <= 1000 and x2 > x1 and y2 > y1


def _normalized_bbox_to_rect(bbox, width, height):
    return {
        'left': int(round((bbox[0] * width) / 1000.0)),
        'top': int(round((bbox[1] * height) / 1000.0)),
        'right': int(round((bbox[2] * width) / 1000.0)),
        'bottom': int(round((bbox[3] * height) / 1000.0)),
    }


def _bbox_list_to_rect(bbox):
    return {
        'left': int(round(bbox[0])),
        'top': int(round(bbox[1])),
        'right': int(round(bbox[2])),
        'bottom': int(round(bbox[3])),
    }


def _bbox_center(viewport_bbox):
    return {
        'x': int(round((viewport_bbox['left'] + viewport_bbox['right']) / 2.0)),
        'y': int(round((viewport_bbox['top'] + viewport_bbox['bottom']) / 2.0)),
    }


def _scale_bbox(viewport_bbox, model_scale):
    """Map a bbox in model-image coordinates back to CSS viewport coordinates."""
    model_scale = model_scale or {}
    scale_x = model_scale.get('x') or 1.0
    scale_y = model_scale.get('y') or 1.0
    if scale_x == 1.0 and scale_y == 1.0:
        return viewport_bbox
    return {
        'left': int(round(viewport_bbox['left'] * scale_x)),
        'top': int(round(viewport_bbox['top'] * scale_y)),
        'right': int(round(viewport_bbox['right'] * scale_x)),
        'bottom': int(round(viewport_bbox['bottom'] * scale_y)),
    }


def _viewport_bbox_to_page_bbox(viewport_bbox, scroll_position):
    return {
        'left': viewport_bbox['left'] + scroll_position.get('x', 0),
        'top': viewport_bbox['top'] + scroll_position.get('y', 0),
        'width': viewport_bbox['right'] - viewport_bbox['left'],
        'height': viewport_bbox['bottom'] - viewport_bbox['top'],
    }


def _bbox_to_draw_rect(viewport_bbox, screenshot_size):
    max_width = screenshot_size.get('width', viewport_bbox['right'])
    max_height = screenshot_size.get('height', viewport_bbox['bottom'])
    return (
        max(0, min(int(viewport_bbox['left']), int(max_width))),
        max(0, min(int(viewport_bbox['top']), int(max_height))),
        max(0, min(int(viewport_bbox['right']), int(max_width))),
        max(0, min(int(viewport_bbox['bottom']), int(max_height))),
    )


def _dedupe_bboxes(items):
    seen = set()
    result = []
    for item in items:
        key = (item['left'], item['top'], item['right'], item['bottom'])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _join_errors(errors):
    if not errors:
        return None
    if isinstance(errors, list):
        return '; '.join([str(i) for i in errors if i])
    return str(errors)


def _model_debug_options(options, prompt, prefix_suffix='model'):
    options = options or {}
    enabled = options.get('debug_model') or options.get('debug_request') or options.get('debug')
    if not enabled:
        return None
    debug_dir = options.get('debug_model_dir') or options.get('debug_dir')
    prefix = options.get('debug_model_prefix') or '{}_{}'.format(_safe_name(prompt) or 'request', prefix_suffix)
    return {'enabled': True, 'dir': debug_dir, 'prefix': prefix}
