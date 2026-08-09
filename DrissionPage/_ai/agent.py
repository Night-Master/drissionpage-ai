# -*- coding:utf-8 -*-
"""
Public AI agent for DrissionPage.
"""
from base64 import b64decode
from io import BytesIO
from json import dumps
from pathlib import Path
from tempfile import gettempdir
from time import sleep, strftime

from .adapter import DrissionPageAIAdapter
from .cache import AIPlanCache
from .context import build_context, normalize_screenshot_to_css_pixels
from .extractor import AIExtractor
from .locator import AILocator, _bbox_center, _interpret_model_bbox
from .model import OpenAICompatibleModel
from .planner import AIPlanner
from .report import AIReport
from .yaml_runner import AIYamlRunner


class DrissionPageAgent(object):
    def __init__(self, page):
        self._page = page
        self._adapter = DrissionPageAIAdapter(page)
        self._model = OpenAICompatibleModel()
        self._locator = AILocator(self._adapter, self._model)
        self._extractor = AIExtractor(self._adapter, self._model)
        self._report = AIReport(self._adapter)
        self._cache = AIPlanCache()
        self._planner = AIPlanner(self._adapter, self._model, self, cache=self._cache)
        self._yaml_runner = AIYamlRunner(self)
        self._frozen_context = None
        self._ai_act_context = ''

    def aiAct(self, prompt, options=None):
        result = self._planner.execute(prompt, options=options)
        self.recordToReport('aiAct', result)
        return result

    def ai(self, prompt, options=None):
        return self.aiAct(prompt, options=options)

    def aiTap(self, locate, options=None):
        result = self.aiLocate(locate, options=options)
        self._adapter.click_point(result.center_page.get('x'), result.center_page.get('y'))
        self.recordToReport('aiTap', {'locate': locate, 'result': result.as_dict()})
        return result

    def aiHover(self, locate, options=None):
        result = self.aiLocate(locate, options=options)
        self._adapter.hover_point(result.center_page.get('x'), result.center_page.get('y'))
        self.recordToReport('aiHover', {'locate': locate, 'result': result.as_dict()})
        return result

    def aiInput(self, locate, opt=None, options=None):
        if options is not None:
            if opt is not None:
                raise ValueError('aiInput() only accepts one of opt or options.')
            opt = options
        options = opt if isinstance(opt, dict) else {'value': opt}
        value = options.get('value')
        if value is None:
            raise ValueError('aiInput() requires a value.')
        clear = options.get('clear', True)
        result = self.aiLocate(locate, options=options)
        input_target = self._adapter.input_at_point(result.center_page.get('x'), result.center_page.get('y'),
                                                    value, clear=clear)
        payload = {'locate': locate, 'value': value, 'result': result.as_dict()}
        if input_target is not None and input_target is not result.element:
            payload['input_target'] = {
                'tag': getattr(input_target, 'tag', None),
                'xpath': input_target.run_js('return this && (function(el){if (el===document.documentElement) return "/html"; if (el===document.body) return "/html/body"; const parts=[]; while(el&&el.nodeType===1&&el!==document.documentElement){let index=1; let sibling=el.previousElementSibling; while(sibling){if(sibling.tagName===el.tagName) index+=1; sibling=sibling.previousElementSibling;} parts.unshift("/"+el.tagName.toLowerCase()+"["+index+"]"); el=el.parentElement; if(el===document.body){parts.unshift("/html/body"); break;}} return parts.join("");})(this);')
            }
        self.recordToReport('aiInput', payload)
        return result

    def aiKeyboardPress(self, locate=None, opt=None):
        target = None
        keys = None
        if isinstance(opt, dict):
            keys = opt.get('key') or opt.get('keys')
            if locate is not None:
                target = self.aiLocate(locate, options=opt).element
        elif opt is None:
            keys = locate
        else:
            target = self.aiLocate(locate).element
            keys = opt
        if keys is None:
            raise ValueError('aiKeyboardPress() requires key or keys.')
        self._adapter.keyboard_press(keys, element=target)
        self.recordToReport('aiKeyboardPress', {'keys': keys, 'locate': locate if opt is not None else None})
        return True

    def aiScroll(self, locate=None, opt=None):
        if isinstance(locate, dict) and opt is None:
            opt = locate
            locate = opt.get('locate')
        options = opt or {}
        direction = options.get('direction', 'down')
        pixel = options.get('pixel', 300)
        center = options.get('center')
        if isinstance(locate, str) and not options and locate.lower() in ('up', 'down', 'left', 'right', 'top', 'bottom'):
            direction = locate
            locate = None
        target = self.aiLocate(locate, options=options).element if locate else None
        self._adapter.scroll(locate=target, direction=direction, pixel=pixel, center=center)
        self.recordToReport('aiScroll', {'locate': locate, 'direction': direction, 'pixel': pixel})
        return True

    def aiDoubleClick(self, locate, options=None):
        result = self.aiLocate(locate, options=options)
        self._adapter.double_click_point(result.center_page.get('x'), result.center_page.get('y'))
        self.recordToReport('aiDoubleClick', {'locate': locate, 'result': result.as_dict()})
        return result

    def aiRightClick(self, locate, options=None):
        result = self.aiLocate(locate, options=options)
        self._adapter.right_click_point(result.center_page.get('x'), result.center_page.get('y'))
        self.recordToReport('aiRightClick', {'locate': locate, 'result': result.as_dict()})
        return result

    def aiTapAt(self, bbox, coord_type=None, options=None):
        """Click by model-native coordinates (bbox [x1, y1, x2, y2] or point [x, y]).

        coord_type declares the coordinate space: 'css' (absolute screenshot pixels) or
        'normalized' (0-1000). When omitted, the format is auto-detected the same way as
        aiLocate model output.
        """
        if isinstance(bbox, (list, tuple)) and len(bbox) == 2:
            bbox = [bbox[0], bbox[1], bbox[0] + 1, bbox[1] + 1]
        prefer_normalized = None
        if isinstance(coord_type, str):
            hint = coord_type.strip().lower()
            if hint in ('normalized', 'normalized_1000', '1000'):
                prefer_normalized = True
            elif hint in ('css', 'pixel', 'pixels', 'absolute'):
                prefer_normalized = False
        metrics = self._adapter.get_metrics()
        normalized = normalize_screenshot_to_css_pixels(self._adapter.screenshot_base64(), metrics)
        candidates = _interpret_model_bbox({'bbox': bbox}, normalized['size'],
                                           model_name=getattr(self._model, 'model', ''),
                                           prefer_normalized=prefer_normalized)
        if not candidates:
            raise RuntimeError('aiTapAt() could not interpret coordinates: {}'.format(bbox))
        center = _bbox_center(candidates[0])
        point = self._adapter.viewport_to_page_point(center['x'], center['y'], metrics=metrics)
        self._adapter.click_point(point['x'], point['y'])
        payload = {'bbox': bbox, 'coord_type': coord_type, 'center_viewport': center, 'center_page': point}
        options = options or {}
        if options.get('debug') or options.get('debug_model') or options.get('debug_request'):
            payload['debug'] = _dump_tap_at_debug(bbox, coord_type, candidates[0], center, point,
                                                  normalized, metrics, options)
        self.recordToReport('aiTapAt', payload)
        return payload

    def aiAsk(self, prompt, options=None):
        return self.aiString(prompt, options=options)

    def aiQuery(self, data_demand, options=None):
        return self._extractor.query(data_demand, frozen_context=self._context_for_read(options),
                                     ai_context=self._ai_act_context, options=options)

    def aiQueryImages(self, prompt, options=None):
        return self._extractor.query_images(prompt, frozen_context=self._context_for_read(options),
                                            ai_context=self._ai_act_context, options=options)

    def aiBoolean(self, prompt, options=None):
        return self._extractor.boolean(prompt, frozen_context=self._context_for_read(options),
                                       ai_context=self._ai_act_context, options=options)

    def aiNumber(self, prompt, options=None):
        return self._extractor.number(prompt, frozen_context=self._context_for_read(options),
                                      ai_context=self._ai_act_context, options=options)

    def aiString(self, prompt, options=None):
        return self._extractor.string(prompt, frozen_context=self._context_for_read(options),
                                      ai_context=self._ai_act_context, options=options)

    def aiAssert(self, assertion, error_msg=None, options=None):
        result = self._extractor.assert_(assertion, error_msg=error_msg,
                                         frozen_context=self._context_for_read(options),
                                         ai_context=self._ai_act_context, options=options)
        self.recordToReport('aiAssert', {'assertion': assertion, 'result': result})
        return result

    def aiLocate(self, locate, options=None):
        result = self._locator.locate(locate, options=options, frozen_context=self._context_for_read(options),
                                      ai_context=self._ai_act_context)
        return result

    def aiWaitFor(self, assertion, options=None):
        options = options or {}
        timeout = options.get('timeout', 10)
        interval = options.get('interval', 1)
        result = self._extractor.wait_for(assertion, timeout=timeout, interval=interval,
                                          ai_context=self._ai_act_context, options=options)
        self.recordToReport('aiWaitFor', {'assertion': assertion, 'timeout': timeout, 'interval': interval})
        return result

    def runYaml(self, yaml_script_content):
        result = self._yaml_runner.run(yaml_script_content)
        self.recordToReport('runYaml', result)
        return result

    def setAIActContext(self, ai_act_context):
        self._ai_act_context = ai_act_context or ''
        return self

    def evaluateJavaScript(self, script):
        return self._adapter.evaluate_javascript(script)

    def recordToReport(self, title=None, options=None):
        return self._report.record(title=title, payload=options or {})

    def freezePageContext(self):
        self._frozen_context = build_context(self._adapter, max_elements=180, include_html=True)
        return self._frozen_context

    def unfreezePageContext(self):
        self._frozen_context = None
        return self

    def _unstableLogContent(self):
        return self._report.logs()

    def _context_for_read(self, options=None):
        if options and options.get('refresh_context'):
            return None
        return self._frozen_context

    def _execute_step(self, step, options=None):
        options = options or {}
        step = dict(step)
        action = step.pop('action', None)
        if not action:
            raise ValueError('AI step is missing action.')
        if action == 'ai':
            action = 'aiAct'
        if action == 'done':
            return step.get('summary')
        if action == 'Sleep':
            time_ms = int(step.get('timeMs') or step.get('time_ms') or 0)
            if time_ms > 0:
                sleep(float(time_ms) / 1000.0)
            return {'slept_ms': time_ms}

        merged_options = dict(options)
        step_options = step.pop('options', None)
        if isinstance(step_options, dict):
            merged_options.update(step_options)

        if action in ('aiTap', 'aiHover', 'aiDoubleClick', 'aiRightClick', 'aiLocate'):
            target = step.get('target') or step.get('locate') or step.get('prompt')
            return getattr(self, action)(target, options=merged_options)

        if action == 'aiTapAt':
            return self.aiTapAt(step.get('bbox') or step.get('value'),
                                coord_type=step.get('coord_type') or step.get('coordType'),
                                options=merged_options)

        if action == 'aiInput':
            target = step.get('target') or step.get('locate')
            payload = {
                'value': step.get('value'),
                'clear': step.get('clear', True),
            }
            payload.update(merged_options)
            return self.aiInput(target, payload)

        if action == 'aiKeyboardPress':
            target = step.get('target') or step.get('locate')
            payload = {
                'keys': step.get('keys') or step.get('key'),
            }
            payload.update(merged_options)
            return self.aiKeyboardPress(target, payload) if target else self.aiKeyboardPress(payload['keys'])

        if action == 'aiScroll':
            target = step.get('target') or step.get('locate')
            payload = {
                'direction': step.get('direction', 'down'),
                'pixel': step.get('pixel', 300),
                'center': step.get('center'),
            }
            payload.update(merged_options)
            return self.aiScroll(target, payload) if target else self.aiScroll(payload)

        if action in ('aiAsk', 'aiString', 'aiBoolean', 'aiNumber'):
            prompt = step.get('prompt') or step.get('question')
            return getattr(self, action)(prompt, options=merged_options)

        if action == 'aiQuery':
            prompt = step.get('data_demand') or step.get('prompt') or step.get('query')
            return self.aiQuery(prompt, options=merged_options)

        if action == 'aiQueryImages':
            prompt = step.get('data_demand') or step.get('prompt') or step.get('query')
            return self.aiQueryImages(prompt, options=merged_options)

        if action == 'aiAssert':
            return self.aiAssert(step.get('assertion'), error_msg=step.get('error_msg'), options=merged_options)

        if action == 'aiWaitFor':
            payload = {
                'timeout': step.get('timeout', 10),
                'interval': step.get('interval', 1),
            }
            payload.update(merged_options)
            return self.aiWaitFor(step.get('assertion'), options=payload)

        if action == 'evaluateJavaScript':
            return self.evaluateJavaScript(step.get('script'))

        if action == 'recordToReport':
            return self.recordToReport(step.get('title'), step.get('payload'))

        if action == 'aiAct':
            return self.aiAct(step.get('prompt'), options=merged_options)

        if action == 'runYaml':
            return self.runYaml(step.get('content') or step.get('yaml_script_content'))

        raise ValueError('Unsupported AI action: {}'.format(action))

    def _serialize_result(self, result):
        if hasattr(result, 'as_dict'):
            return result.as_dict()
        if isinstance(result, (str, int, float, bool)) or result is None:
            return result
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            return [self._serialize_result(i) for i in result]
        return str(result)


def _dump_tap_at_debug(bbox, coord_type, viewport_bbox, center, point, normalized, metrics, options):
    """Dump the screenshot used for tap_at coordinate conversion, plus an annotated copy
    showing the interpreted bbox and the click point."""
    save_dir = Path(options.get('debug_dir') or (Path(gettempdir()) / 'drissionpage_ai_locate_debug'))
    save_dir.mkdir(parents=True, exist_ok=True)
    stem = 'tap_at_{}'.format(strftime('%Y%m%d_%H%M%S'))
    raw_path = save_dir / '{}_raw.png'.format(stem)
    annotated_path = save_dir / '{}_annotated.png'.format(stem)
    meta_path = save_dir / '{}_meta.json'.format(stem)

    image_bytes = b64decode(normalized['base64'])
    raw_path.write_bytes(image_bytes)
    meta_path.write_text(dumps({
        'bbox_input': bbox,
        'coord_type': coord_type,
        'viewport_bbox_interpreted': viewport_bbox,
        'center_viewport': center,
        'center_page': point,
        'screenshot_size': normalized.get('size'),
        'screenshot_actual_size': normalized.get('actual_size'),
        'screenshot_normalized': normalized.get('normalized'),
        'scroll_position': metrics.get('scroll_position', {}),
    }, ensure_ascii=False, indent=2), encoding='utf-8')

    debug = {
        'raw_screenshot_path': str(raw_path),
        'annotated_screenshot_path': None,
        'meta_path': str(meta_path),
    }

    try:
        from PIL import Image, ImageDraw
    except Exception:
        return debug

    css_size = normalized.get('size') or {}
    image = Image.open(BytesIO(image_bytes)).convert('RGBA')
    scale_x = image.width / (css_size.get('width') or image.width)
    scale_y = image.height / (css_size.get('height') or image.height)
    line_width = max(2, int(round(2 * scale_x)))
    cross_r = max(4, int(round(8 * scale_x)))
    draw = ImageDraw.Draw(image)
    draw.rectangle((int(round(viewport_bbox['left'] * scale_x)),
                    int(round(viewport_bbox['top'] * scale_y)),
                    int(round(viewport_bbox['right'] * scale_x)),
                    int(round(viewport_bbox['bottom'] * scale_y))),
                   outline=(59, 130, 246, 255), width=line_width)
    cross_x = int(round(center['x'] * scale_x))
    cross_y = int(round(center['y'] * scale_y))
    draw.line((cross_x - cross_r, cross_y, cross_x + cross_r, cross_y),
              fill=(235, 64, 52, 255), width=line_width)
    draw.line((cross_x, cross_y - cross_r, cross_x, cross_y + cross_r),
              fill=(235, 64, 52, 255), width=line_width)
    image.save(annotated_path, format='PNG')
    debug['annotated_screenshot_path'] = str(annotated_path)
    return debug
