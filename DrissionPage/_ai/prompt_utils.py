# -*- coding:utf-8 -*-
"""
Prompt helpers for multimodal AI inputs.
"""
from base64 import b64encode
from mimetypes import guess_type
from os.path import exists
from pathlib import Path
from re import match

from requests import get


def parse_user_prompt(prompt):
    if isinstance(prompt, str):
        return {
            'text_prompt': prompt,
            'multimodal_prompt': None,
        }

    if isinstance(prompt, dict):
        text_prompt = prompt.get('prompt') or ''
        images = prompt.get('images') or []
        convert_http = bool(prompt.get('convertHttpImage2Base64'))
        multimodal_prompt = None
        if images:
            multimodal_prompt = {
                'images': images,
                'convert_http_image_to_base64': convert_http,
            }
        return {
            'text_prompt': text_prompt,
            'multimodal_prompt': multimodal_prompt,
        }

    return {
        'text_prompt': str(prompt),
        'multimodal_prompt': None,
    }


def prepare_reference_images(multimodal_prompt):
    if not multimodal_prompt or not multimodal_prompt.get('images'):
        return []
    convert_http = multimodal_prompt.get('convert_http_image_to_base64', False)
    prepared = []
    for item in multimodal_prompt.get('images', []):
        name = item.get('name') or 'reference'
        url = item.get('url')
        if not url:
            continue
        prepared.append(_prepare_single_image(name, url, convert_http))
    return prepared


def _prepare_single_image(name, url, convert_http):
    if isinstance(url, str) and url.startswith('data:image/'):
        return {
            'name': name,
            'url': url,
            'format': _image_format_from_data_url(url),
            'is_inline': True,
        }

    if isinstance(url, str) and exists(url):
        path = Path(url)
        image_format = _format_from_name(path.name)
        base64_data = b64encode(path.read_bytes()).decode('ascii')
        return {
            'name': name,
            'url': 'data:image/{};base64,{}'.format(image_format, base64_data),
            'format': image_format,
            'is_inline': True,
            'source_path': str(path),
        }

    if isinstance(url, str) and match(r'^https?://', url):
        if convert_http:
            response = get(url, timeout=30)
            response.raise_for_status()
            image_format = _format_from_name(url)
            base64_data = b64encode(response.content).decode('ascii')
            return {
                'name': name,
                'url': 'data:image/{};base64,{}'.format(image_format, base64_data),
                'format': image_format,
                'is_inline': True,
                'source_url': url,
            }
        return {
            'name': name,
            'url': url,
            'format': _format_from_name(url),
            'is_inline': False,
            'source_url': url,
        }

    return {
        'name': name,
        'url': str(url),
        'format': _format_from_name(str(url)),
        'is_inline': False,
    }


def _format_from_name(name):
    mime, _ = guess_type(str(name))
    if mime and '/' in mime:
        return mime.split('/', 1)[1]
    lowered = str(name).lower()
    if lowered.endswith('.jpg') or lowered.endswith('.jpeg'):
        return 'jpeg'
    if lowered.endswith('.webp'):
        return 'webp'
    return 'png'


def _image_format_from_data_url(url):
    prefix = str(url).split(';', 1)[0]
    if '/' in prefix:
        return prefix.rsplit('/', 1)[-1]
    return 'png'


def should_return_images(prompt, options=None):
    options = options or {}
    if options.get('return_images') or options.get('image_mode'):
        return True
    if not isinstance(prompt, str):
        return False
    text = prompt.strip()
    return '图片' in text and any(key in text for key in ('每个字', '切图', '裁剪', '小图', '返回图片', '一图'))
