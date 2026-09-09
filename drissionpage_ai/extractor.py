# -*- coding:utf-8 -*-
"""
AI-backed data extraction helpers.
"""
from base64 import b64decode, b64encode
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir
from time import perf_counter, sleep

from .context import build_context
from .locator import _interpret_model_bbox
from .prompt_utils import parse_user_prompt, prepare_reference_images


class AIExtractor(object):
    def __init__(self, adapter, model):
        self._adapter = adapter
        self._model = model

    def ask(self, prompt, frozen_context=None, ai_context=None, options=None):
        return self.string(prompt, frozen_context=frozen_context, ai_context=ai_context, options=options)

    def query(self, data_demand, frozen_context=None, ai_context=None, options=None):
        options = options or {}
        context = self._build_query_context(frozen_context=frozen_context, options=options)
        result = self._call_json(
            task='Extract structured data from the current page.',
            prompt=data_demand,
            context=context,
            ai_context=ai_context,
            return_shape='{"value": any, "reason": string}',
            options=options,
        )
        return result.get('value', result)

    def string(self, prompt, frozen_context=None, ai_context=None, options=None):
        options = options or {}
        parsed = parse_user_prompt(prompt)
        text_prompt = parsed['text_prompt']
        reference_images = prepare_reference_images(parsed['multimodal_prompt'])
        context = self._build_query_context(frozen_context=frozen_context, options=options)
        result = self._call_json(
            task='Answer the question with a short string.',
            prompt=text_prompt,
            context=context,
            ai_context=ai_context,
            return_shape='{"value": string, "reason": string}',
            options=options,
            reference_images=reference_images,
        )
        value = result.get('value')
        return '' if value is None else str(value)

    def number(self, prompt, frozen_context=None, ai_context=None, options=None):
        options = options or {}
        parsed = parse_user_prompt(prompt)
        text_prompt = parsed['text_prompt']
        reference_images = prepare_reference_images(parsed['multimodal_prompt'])
        context = self._build_query_context(frozen_context=frozen_context, options=options)
        result = self._call_json(
            task='Answer the question with a number.',
            prompt=text_prompt,
            context=context,
            ai_context=ai_context,
            return_shape='{"value": number, "reason": string}',
            options=options,
            reference_images=reference_images,
        )
        value = result.get('value')
        if isinstance(value, (int, float)):
            return value
        try:
            return float(value)
        except Exception:
            raise RuntimeError('AI number extraction did not return a valid number: {}'.format(value))

    def boolean(self, prompt, frozen_context=None, ai_context=None, options=None):
        options = options or {}
        parsed = parse_user_prompt(prompt)
        text_prompt = parsed['text_prompt']
        reference_images = prepare_reference_images(parsed['multimodal_prompt'])
        context = self._build_query_context(frozen_context=frozen_context, options=options)
        result = self._call_json(
            task='Answer the question with true or false.',
            prompt=text_prompt,
            context=context,
            ai_context=ai_context,
            return_shape='{"value": boolean, "reason": string}',
            options=options,
            reference_images=reference_images,
        )
        return _to_bool(result.get('value'))

    def assert_(self, assertion, error_msg=None, frozen_context=None, ai_context=None, options=None):
        options = options or {}
        parsed = parse_user_prompt(assertion)
        text_prompt = parsed['text_prompt']
        reference_images = prepare_reference_images(parsed['multimodal_prompt'])
        context = self._build_query_context(frozen_context=frozen_context, options=options)
        result = self._call_json(
            task='Judge whether the assertion is true for the current page.',
            prompt=text_prompt,
            context=context,
            ai_context=ai_context,
            return_shape='{"value": boolean, "reason": string}',
            options=options,
            reference_images=reference_images,
        )
        ok = _to_bool(result.get('value'))
        if ok:
            return True
        reason = result.get('reason') or assertion
        raise AssertionError(error_msg or reason)

    def wait_for(self, assertion, timeout=10, interval=1, ai_context=None, options=None):
        end_time = perf_counter() + timeout
        last_error = None
        while perf_counter() < end_time:
            try:
                if self.assert_(assertion, frozen_context=None, ai_context=ai_context, options=options):
                    return True
            except Exception as e:
                last_error = e
            sleep(interval)
        if last_error:
            raise last_error
        raise TimeoutError('aiWaitFor timed out after {} seconds.'.format(timeout))

    def query_images(self, prompt, frozen_context=None, ai_context=None, options=None):
        options = options or {}
        parsed = parse_user_prompt(prompt)
        text_prompt = parsed['text_prompt']
        reference_images = prepare_reference_images(parsed['multimodal_prompt'])
        context = self._build_query_context(frozen_context=frozen_context, options=options)
        result = self._call_json(
            task='Locate image regions on the current page and return crops.',
            prompt=text_prompt,
            context=context,
            ai_context=ai_context,
            return_shape='{"images": [{"name": string, "bbox": [x1, y1, x2, y2], "reason": string}], "reason": string}',
            options=options,
            reference_images=reference_images,
            force_visual_only=True,
        )
        images = []
        for index, item in enumerate(result.get('images', []), start=1):
            bbox_list = _interpret_model_bbox(
                {'bbox': item.get('bbox')},
                context['screenshot_size'],
                model_name=getattr(self._model, 'model', '')
            )
            if not bbox_list:
                continue
            viewport_bbox = bbox_list[0]
            crop = _crop_screenshot(context['screenshot_base64'], viewport_bbox)
            saved_path = _save_crop_if_needed(crop['bytes'], item.get('name') or 'crop', options, index=index)
            images.append({
                'name': item.get('name') or 'crop_{}'.format(index),
                'reason': item.get('reason'),
                'viewport_bbox': viewport_bbox,
                'base64': crop['base64'],
                'format': 'png',
                'path': saved_path,
            })
        return images

    def _call_json(self, task, prompt, context, ai_context=None, return_shape='{"value": string}', options=None,
                   reference_images=None, force_visual_only=False):
        if not self._model.available:
            raise RuntimeError(
                'AI extraction requires model configuration. Set OPENAI_API_KEY/BASE_URL/MODEL.'
            )
        options = options or {}
        reference_images = reference_images or []
        extra_context = ai_context.strip() if isinstance(ai_context, str) else ''
        pure_visual = options.get('pure_visual', True) or force_visual_only
        include_elements = options.get('include_elements', not pure_visual)
        include_html = options.get('include_html', False)

        if pure_visual:
            system_prompt = (
                'You answer questions about the current webpage primarily from the screenshot. '
                'Use only what is visually present in the screenshot unless extra structured context is explicitly provided. '
                'Return JSON only.'
            )
        else:
            system_prompt = (
                'You answer questions about the current webpage using the screenshot and any provided structured context. '
                'Return JSON only.'
            )

        parts = [
            'Task: {task}',
            'Question: {prompt}',
            'Extra context: {extra_context}',
            'Page title: {title}',
            'Page url: {url}',
        ]
        if include_elements and context.get('element_summary'):
            parts.append('Visible elements:\n{summary}')
        if include_html and context.get('html'):
            parts.append('HTML excerpt:\n{html}')
        parts.append('Return JSON with shape: {return_shape}')

        user_prompt = '\n\n'.join(parts).format(
            task=task,
            prompt=prompt,
            extra_context=extra_context or 'none',
            title=context['title'],
            url=context['url'],
            summary=context.get('element_summary', ''),
            html=context.get('html', ''),
            return_shape=return_shape
        )
        model_debug = _extractor_model_debug_options(options, prompt)
        return self._model.complete_json(system_prompt, user_prompt,
                                         image_base64=context['screenshot_base64'],
                                         image_format=context['screenshot_format'],
                                         reference_images=reference_images,
                                         debug=model_debug)

    def _build_query_context(self, frozen_context=None, options=None):
        options = options or {}
        include_html = options.get('include_html', False)
        max_elements = options.get('max_elements', 180)
        return build_context(self._adapter, frozen_context=frozen_context,
                             include_html=include_html, max_elements=max_elements)


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    value = str(value or '').strip().lower()
    if value in ('true', '1', 'yes', 'y'):
        return True
    if value in ('false', '0', 'no', 'n', ''):
        return False
    raise RuntimeError('AI boolean extraction did not return a valid boolean: {}'.format(value))


def _extractor_model_debug_options(options, prompt):
    options = options or {}
    enabled = options.get('debug_model') or options.get('debug_request') or options.get('debug')
    if not enabled:
        return None
    debug_dir = options.get('debug_model_dir') or options.get('debug_dir')
    return {
        'enabled': True,
        'dir': debug_dir,
        'prefix': '{}_query'.format(str(prompt or 'query')[:30]),
    }


def _crop_screenshot(screenshot_base64, viewport_bbox):
    from PIL import Image
    image = Image.open(BytesIO(b64decode(screenshot_base64))).convert('RGBA')
    crop = image.crop((viewport_bbox['left'], viewport_bbox['top'], viewport_bbox['right'], viewport_bbox['bottom']))
    buf = BytesIO()
    crop.save(buf, format='PNG')
    image_bytes = buf.getvalue()
    return {
        'bytes': image_bytes,
        'base64': b64encode(image_bytes).decode('ascii'),
    }


def _save_crop_if_needed(image_bytes, name, options, index=1):
    save_dir = options.get('save_image_dir') or options.get('debug_dir')
    if not save_dir:
        return None
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    path = save_dir / 'query_image_{}_{}.png'.format(index, _safe_name(name))
    path.write_bytes(image_bytes)
    return str(path)


def _safe_name(text, limit=40):
    text = ''.join([c if c.isalnum() or c in ('_', '-') else '_' for c in str(text or '')]).strip('_')
    return text[:limit] or 'image'
