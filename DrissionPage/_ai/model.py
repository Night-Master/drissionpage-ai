# -*- coding:utf-8 -*-
"""
Minimal OpenAI-compatible client for DrissionPage AI, backed by the official openai SDK.
"""
from base64 import b64decode
from json import dumps, loads
from os import getenv
from pathlib import Path
from re import DOTALL, search, sub
from tempfile import gettempdir
from time import strftime

from openai import OpenAI


class OpenAICompatibleModel(object):
    def __init__(self, base_url=None, api_key=None, model=None, timeout=None, temperature=None, max_tokens=None):
        self.base_url = base_url or getenv('OPENAI_BASE_URL') or 'https://api.openai.com/v1'
        self.api_key = api_key or getenv('OPENAI_API_KEY')
        self.model = model or getenv('OPENAI_MODEL') or 'gpt-4o-mini'
        self.timeout = float(timeout if timeout is not None else getenv('DP_AI_TIMEOUT', '90'))
        self.temperature = float(temperature if temperature is not None
                                 else getenv('DP_AI_TEMPERATURE', '0'))
        self.max_tokens = int(max_tokens if max_tokens is not None else getenv('DP_AI_MAX_TOKENS', '1200'))
        self.base_url = _normalize_base_url(self.base_url)
        self.last_debug = {}
        self._client = None

    @property
    def available(self):
        return bool(self.api_key)

    def complete_json(self, system_prompt, user_prompt, image_base64=None, image_format='png',
                      reference_images=None, debug=None):
        content = self._complete(system_prompt, user_prompt, image_base64=image_base64, image_format=image_format,
                                 reference_images=reference_images,
                                 response_format={'type': 'json_object'}, debug=debug)
        return _safe_load_json(content)

    def complete_text(self, system_prompt, user_prompt, image_base64=None, image_format='png',
                      reference_images=None, debug=None):
        return self._complete(system_prompt, user_prompt, image_base64=image_base64, image_format=image_format,
                              reference_images=reference_images, debug=debug)

    def _get_client(self):
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        return self._client

    def _complete(self, system_prompt, user_prompt, image_base64=None, image_format='png',
                  reference_images=None, response_format=None, debug=None):
        if not self.api_key:
            raise RuntimeError('AI model is not configured. Set OPENAI_API_KEY '
                               '(and OPENAI_BASE_URL/OPENAI_MODEL for compatible endpoints).')
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': _build_user_content(
                    user_prompt,
                    image_base64=image_base64,
                    image_format=image_format,
                    reference_images=reference_images,
                )},
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
        }
        if response_format:
            payload['response_format'] = response_format
        self.last_debug = {}
        debug_info = _prepare_debug_dump(
            self.base_url, payload, system_prompt, user_prompt, image_base64, image_format, reference_images, debug
        )
        if debug_info:
            self.last_debug = debug_info
        response = self._get_client().chat.completions.create(**payload)
        if debug_info:
            _finalize_debug_dump(debug_info, response)
            self.last_debug = debug_info
        return _extract_message_text(response.model_dump())


def _build_user_content(text, image_base64=None, image_format='png', reference_images=None):
    reference_images = reference_images or []
    if not image_base64 and not reference_images:
        return text
    content = [{'type': 'text', 'text': text}]
    if image_base64:
        content.append({
            'type': 'image_url',
            'image_url': {
                'url': 'data:image/{};base64,{}'.format(image_format, image_base64)
            }
        })
    for image in reference_images:
        content.append({'type': 'text', 'text': "Reference image '{}':".format(image.get('name', 'reference'))})
        content.append({
            'type': 'image_url',
            'image_url': {
                'url': image.get('url')
            }
        })
    return content


def _normalize_base_url(base_url):
    base_url = str(base_url or '').rstrip('/')
    if base_url.endswith('/chat/completions'):
        base_url = base_url[:-len('/chat/completions')]
    return base_url


def _prepare_debug_dump(url, payload, system_prompt, user_prompt, image_base64, image_format, reference_images, debug):
    if not (_debug_enabled(debug) or _env_debug_enabled()):
        return {}

    save_dir = Path(_debug_dir(debug))
    save_dir.mkdir(parents=True, exist_ok=True)
    prefix = _debug_prefix(debug) or 'model_request'
    timestamp = strftime('%Y%m%d_%H%M%S')
    stem = '{}_{}'.format(prefix, timestamp)

    prompt_system_path = save_dir / '{}_system_prompt.txt'.format(stem)
    prompt_user_path = save_dir / '{}_user_prompt.txt'.format(stem)
    request_json_path = save_dir / '{}_request.json'.format(stem)
    request_meta_path = save_dir / '{}_meta.json'.format(stem)
    image_path = save_dir / '{}_image.{}'.format(stem, image_format)
    response_json_path = save_dir / '{}_response.json'.format(stem)
    response_text_path = save_dir / '{}_response.txt'.format(stem)

    prompt_system_path.write_text(system_prompt, encoding='utf-8')
    prompt_user_path.write_text(user_prompt, encoding='utf-8')

    redacted_payload = loads(dumps(payload))
    if isinstance(redacted_payload.get('messages'), list):
        for message in redacted_payload['messages']:
            if isinstance(message, dict) and isinstance(message.get('content'), list):
                for item in message['content']:
                    if isinstance(item, dict) and item.get('type') == 'image_url':
                        item['image_url'] = {'url': '<saved to image file>'}

    request_json_path.write_text(dumps(redacted_payload, ensure_ascii=False, indent=2), encoding='utf-8')

    meta = {
        'url': url,
        'model': payload.get('model'),
        'temperature': payload.get('temperature'),
        'max_tokens': payload.get('max_tokens'),
        'response_format': payload.get('response_format'),
        'has_image': bool(image_base64),
    }
    request_meta_path.write_text(dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

    image_saved_path = None
    if image_base64:
        image_path.write_bytes(b64decode(image_base64))
        image_saved_path = str(image_path)
    reference_image_paths = []
    for index, image in enumerate(reference_images or [], start=1):
        image_url = image.get('url')
        if isinstance(image_url, str) and image_url.startswith('data:image/'):
            fmt = _image_format_from_data_url(image_url)
            image_file = save_dir / '{}_ref_{}_{}.{}'.format(
                stem, index, _safe_name(image.get('name', 'reference')), fmt
            )
            image_file.write_bytes(b64decode(image_url.split(',', 1)[-1]))
            reference_image_paths.append(str(image_file))
        elif image_url:
            reference_image_paths.append(str(image_url))

    return {
        'dir': str(save_dir),
        'system_prompt_path': str(prompt_system_path),
        'user_prompt_path': str(prompt_user_path),
        'request_json_path': str(request_json_path),
        'request_meta_path': str(request_meta_path),
        'image_path': image_saved_path,
        'reference_image_paths': reference_image_paths,
        'response_json_path': str(response_json_path),
        'response_text_path': str(response_text_path),
    }


def _finalize_debug_dump(debug_info, response):
    data = response.model_dump()
    Path(debug_info['response_text_path']).write_text(_extract_message_text(data) or '', encoding='utf-8')
    Path(debug_info['response_json_path']).write_text(dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _debug_enabled(debug):
    return bool(isinstance(debug, dict) and debug.get('enabled'))


def _env_debug_enabled():
    value = str(getenv('DP_AI_DEBUG_REQUESTS', '')).strip().lower()
    return value in ('1', 'true', 'yes', 'on')


def _debug_dir(debug):
    if isinstance(debug, dict) and debug.get('dir'):
        return debug['dir']
    return getenv('DP_AI_DEBUG_DIR') or str(Path(gettempdir()) / 'drissionpage_ai_model_debug')


def _debug_prefix(debug):
    if isinstance(debug, dict) and debug.get('prefix'):
        return _safe_name(debug['prefix'])
    return _safe_name(getenv('DP_AI_DEBUG_PREFIX', 'model_request'))


def _safe_name(text, limit=60):
    text = sub(r'[^0-9a-zA-Z一-鿿_-]+', '_', str(text or '')).strip('_')
    return text[:limit] or 'model_request'


def _image_format_from_data_url(url):
    header = str(url).split(';', 1)[0]
    if '/' in header:
        return header.rsplit('/', 1)[-1]
    return 'png'


def _extract_message_text(data):
    choices = data.get('choices') or []
    if not choices:
        raise RuntimeError('AI model returned no choices.')
    message = choices[0].get('message') or {}
    content = message.get('content', '')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    texts.append(item.get('text', ''))
                elif 'text' in item:
                    texts.append(item.get('text', ''))
        return '\n'.join([i for i in texts if i])
    return str(content)


def _safe_load_json(content):
    content = content.strip()
    if not content:
        raise RuntimeError('AI model returned empty JSON content.')
    try:
        return loads(content)
    except Exception:
        pass

    content = sub(r'^```(?:json)?\s*', '', content)
    content = sub(r'\s*```$', '', content)
    try:
        return loads(content)
    except Exception:
        pass

    matched = search(r'(\{.*\}|\[.*\])', content, DOTALL)
    if not matched:
        raise RuntimeError('AI model did not return valid JSON: {}'.format(content))
    return loads(matched.group(1))
