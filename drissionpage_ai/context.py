# -*- coding:utf-8 -*-
"""
Context builders for DrissionPage AI.
"""
from base64 import b64decode, b64encode
from io import BytesIO
from os import getenv
from struct import unpack

DEFAULT_MODEL_SCREENSHOT_WIDTH = 1920
DEFAULT_MODEL_SCREENSHOT_HEIGHT = 1080


def build_context(adapter, frozen_context=None, max_elements=180, include_html=False):
    if frozen_context:
        return frozen_context

    metrics = adapter.get_metrics()
    screenshot_base64 = adapter.screenshot_base64()
    normalized = normalize_screenshot_to_css_pixels(screenshot_base64, metrics)
    capped = cap_screenshot_for_model(normalized)
    elements = adapter.extract_elements(max_items=max_elements)
    summary = summarize_elements(elements)
    context = {
        'url': adapter.url,
        'title': adapter.title,
        'metrics': metrics,
        'elements': elements,
        'element_summary': summary,
        'screenshot_base64': capped['base64'],
        'screenshot_format': 'png',
        'screenshot_size': capped['size'],
        'screenshot_actual_size': capped['actual_size'],
        'screenshot_scale_x': normalized['scale_x'],
        'screenshot_scale_y': normalized['scale_y'],
        'screenshot_normalized': normalized['normalized'] or capped['capped'],
        'screenshot_css_source': normalized['css_source'],
        'screenshot_css_size': normalized['size'],
        'screenshot_model_scale': capped['model_scale'],
    }
    if include_html:
        context['html'] = adapter.html[:12000]
    return context


def normalize_screenshot_to_css_pixels(base64_data, metrics):
    actual_width, actual_height = get_png_size(base64_data)
    css_width, css_height, css_source = choose_css_reference_size(metrics, actual_width, actual_height)
    result = {
        'base64': base64_data,
        'size': {'width': css_width, 'height': css_height},
        'actual_size': {'width': actual_width, 'height': actual_height},
        'scale_x': _safe_scale(actual_width, css_width),
        'scale_y': _safe_scale(actual_height, css_height),
        'normalized': False,
        'css_source': css_source,
    }
    if not actual_width or not actual_height or not css_width or not css_height:
        return result
    if actual_width == css_width and actual_height == css_height:
        result['normalized'] = True
        return result

    try:
        from PIL import Image
    except Exception:
        return result

    image = Image.open(BytesIO(b64decode(base64_data)))
    image = image.resize((int(css_width), int(css_height)), Image.LANCZOS)
    buf = BytesIO()
    image.save(buf, format='PNG')
    result['base64'] = b64encode(buf.getvalue()).decode('ascii')
    result['normalized'] = True
    return result


def cap_screenshot_for_model(normalized, max_width=None, max_height=None):
    """Downscale the CSS-sized screenshot so the image sent to the model fits a
    1080p-class budget (default 1920x1080, override with DP_AI_SCREENSHOT_MAX_WIDTH /
    DP_AI_SCREENSHOT_MAX_HEIGHT, set to 0 to disable). The page itself is untouched;
    'model_scale' maps model-image coordinates back to CSS viewport coordinates."""
    size = normalized.get('size') or {}
    css_width = int(size.get('width') or 0)
    css_height = int(size.get('height') or 0)
    max_width = _max_dimension('DP_AI_SCREENSHOT_MAX_WIDTH', max_width, DEFAULT_MODEL_SCREENSHOT_WIDTH)
    max_height = _max_dimension('DP_AI_SCREENSHOT_MAX_HEIGHT', max_height, DEFAULT_MODEL_SCREENSHOT_HEIGHT)
    result = {
        'base64': normalized['base64'],
        'size': dict(size),
        'actual_size': dict(normalized.get('actual_size') or {}),
        'capped': False,
        'model_scale': {'x': 1.0, 'y': 1.0},
    }
    if not css_width or not css_height or not max_width or not max_height:
        return result
    if css_width <= max_width and css_height <= max_height:
        return result

    scale = min(float(max_width) / css_width, float(max_height) / css_height)
    model_width = max(1, int(round(css_width * scale)))
    model_height = max(1, int(round(css_height * scale)))
    try:
        from PIL import Image
    except Exception:
        return result

    image = Image.open(BytesIO(b64decode(normalized['base64'])))
    image = image.resize((model_width, model_height), Image.LANCZOS)
    buf = BytesIO()
    image.save(buf, format='PNG')
    result['base64'] = b64encode(buf.getvalue()).decode('ascii')
    result['size'] = {'width': model_width, 'height': model_height}
    result['actual_size'] = {'width': model_width, 'height': model_height}
    result['capped'] = True
    result['model_scale'] = {'x': float(css_width) / model_width, 'y': float(css_height) / model_height}
    return result


def _max_dimension(env_name, explicit, default):
    if explicit is not None:
        return int(explicit)
    raw = str(getenv(env_name, '')).strip().lower()
    if raw in ('0', 'none', 'off', 'false', 'disable', 'disabled'):
        return 0
    if raw:
        try:
            return int(raw)
        except Exception:
            pass
    return default


def summarize_elements(elements):
    lines = []
    for item in elements:
        lines.append(
            '[{index}] tag={tag} interactive={interactive} text="{text}" aria="{aria_label}" '
            'placeholder="{placeholder}" title="{title}" alt="{alt}" value="{value}" role="{role}" '
            'xpath="{xpath}" rect={rect}'.format(
                index=item.get('index'),
                tag=item.get('tag', ''),
                interactive=item.get('interactive', False),
                text=_short(item.get('text')),
                aria_label=_short(item.get('aria_label')),
                placeholder=_short(item.get('placeholder')),
                title=_short(item.get('title')),
                alt=_short(item.get('alt')),
                value=_short(item.get('value')),
                role=_short(item.get('role')),
                xpath=item.get('xpath', ''),
                rect=item.get('rect_page', {}),
            )
        )
    return '\n'.join(lines)


def get_png_size(base64_data):
    try:
        raw = b64decode(base64_data)
    except Exception:
        return 0, 0
    if len(raw) < 24 or raw[:8] != b'\x89PNG\r\n\x1a\n':
        return 0, 0
    return unpack('>II', raw[16:24])


def _short(text, limit=120):
    if text is None:
        return ''
    text = ' '.join(str(text).split())
    return text[:limit]


def _safe_scale(real_size, css_size):
    if not real_size or not css_size:
        return 1
    return float(real_size) / float(css_size)


def choose_css_reference_size(metrics, actual_width, actual_height):
    candidates = []
    dpr = metrics.get('dpr') or 1
    for name in ('inner_size', 'viewport_size', 'client_size'):
        size = metrics.get(name) or {}
        width = int(size.get('width') or 0)
        height = int(size.get('height') or 0)
        if width <= 0 or height <= 0:
            continue
        score = _candidate_score(actual_width, actual_height, width, height, dpr)
        candidates.append((score, name, width, height))

    if not candidates:
        return 0, 0, 'unknown'
    candidates.sort(key=lambda item: item[0])
    _, name, width, height = candidates[0]
    return width, height, name


def _candidate_score(actual_width, actual_height, css_width, css_height, dpr):
    scale_x = _safe_scale(actual_width, css_width)
    scale_y = _safe_scale(actual_height, css_height)
    aspect_actual = float(actual_width) / float(actual_height) if actual_height else 0
    aspect_css = float(css_width) / float(css_height) if css_height else 0
    return (
        abs(scale_x - scale_y),
        abs(scale_x - dpr) + abs(scale_y - dpr),
        abs(aspect_actual - aspect_css),
        abs(actual_width - css_width * dpr) + abs(actual_height - css_height * dpr),
    )
