# -*- coding:utf-8 -*-
"""
ReAct loop for aiAct(), driven by the OpenAI Agents SDK.
"""
from base64 import b64decode, b64encode
from io import BytesIO
from json import dumps, loads
from pathlib import Path
from re import sub
from time import strftime
from typing import Optional

from .context import build_context, normalize_screenshot_to_css_pixels
from .locator import _interpret_model_bbox
from .model import _resolve_debug_dir

DEFAULT_MAX_TURNS = 40
REACT_IMAGE_SIZE = 1000


class AIPlanner(object):
    def __init__(self, adapter, model, agent, cache=None):
        self._adapter = adapter
        self._model = model
        self._agent = agent
        self._cache = cache
        self._sdk_client = None

    def execute(self, prompt, options=None):
        options = options or {}
        cacheable = options.get('cacheable') is not False
        max_turns = int(options.get('max_turns') or options.get('replanning_cycle_limit')
                        or options.get('replan_times') or DEFAULT_MAX_TURNS)
        cache_key = self._make_cache_key(prompt)

        if cacheable and not options.get('force_replan') and self._cache:
            cached = self._cache.get(cache_key)
            if cached and cached.get('yaml_flow'):
                cached_result = self._agent.runYaml({'steps': cached['yaml_flow']})
                return {
                    'prompt': prompt,
                    'from_cache': True,
                    'yaml_flow': cached['yaml_flow'],
                    'results': cached_result.get('results', []),
                    'replanned': 0,
                    'history': [],
                }

        if not self._model.available:
            raise RuntimeError(
                'aiAct requires model configuration. Set OPENAI_API_KEY/BASE_URL/MODEL.'
            )

        from agents import Agent, ModelSettings, Runner, set_tracing_disabled
        from agents.exceptions import MaxTurnsExceeded

        set_tracing_disabled(True)

        context = build_context(
            self._adapter,
            frozen_context=self._agent._context_for_read(options),
            max_elements=options.get('max_elements', 120),
            include_html=False,
        )

        yaml_flow = []
        all_results = []
        react_agent = Agent(
            name='drissionpage-ai-act',
            instructions=self._instructions(),
            model=_vision_chat_completions_model_class()(model=self._model.model,
                                                         openai_client=self._get_sdk_client()),
            model_settings=ModelSettings(temperature=self._model.temperature,
                                         max_tokens=self._model.max_tokens),
            tools=self._build_tools(yaml_flow, all_results, options),
        )

        hooks = _make_react_debug_hooks(prompt, options, model_name=self._model.model) \
            if _debug_enabled(options) else None

        try:
            run_result = Runner.run_sync(react_agent, self._initial_input(prompt, context),
                                         max_turns=max_turns, hooks=hooks)
        except MaxTurnsExceeded as e:
            raise RuntimeError(
                'aiAct exceeded the max thinking rounds (max_turns={}).'.format(max_turns)
            ) from e

        if cacheable and self._cache:
            self._cache.set(cache_key, {'yaml_flow': yaml_flow})

        history = self._serialize_history(run_result)
        result = {
            'prompt': prompt,
            'from_cache': False,
            'yaml_flow': yaml_flow,
            'results': all_results,
            'replanned': max(0, len(all_results) - 1),
            'history': history,
            'final_output': run_result.final_output,
        }
        self._dump_debug(prompt, result, options)
        return result

    def _get_sdk_client(self):
        if self._sdk_client is None:
            from openai import AsyncOpenAI
            self._sdk_client = AsyncOpenAI(api_key=self._model.api_key, base_url=self._model.base_url,
                                           timeout=self._model.timeout)
        return self._sdk_client

    def _instructions(self):
        return (
            'You are a web automation agent controlling a real browser through tools.\n'
            'The user provides an instruction and the latest page screenshot.\n'
            'Work in a ReAct loop:\n'
            '1. Observe the latest screenshot.\n'
            '2. Decide the next single action and call the matching tool.\n'
            '3. After each tool call you receive the newest screenshot as a new image message. '
            'Re-observe it and continue.\n\n'
            'Rules:\n'
            '- To click anything, call tap_at with the bounding box you read directly from the '
            'screenshot, in 0-{size} coordinates (every screenshot is a {size}x{size} square '
            'image, so the pixel coordinates you see in it are the same thing).\n'
            '- To drag something (e.g. a slider onto its gap), call drag with the source and '
            'target bounding boxes in the same 0-{size} coordinates.\n'
            '- To type text, call input_text with the target field description and the value.\n'
            '- If an action fails, recover and try another approach.\n'
            '- Use the same language as the user instruction in your replies.\n'
            '- When the instruction is fully accomplished, stop calling tools and reply with a short summary.'
        ).format(size=REACT_IMAGE_SIZE)

    def _initial_input(self, prompt, context):
        text = (
            'User instruction:\n{prompt}\n\n'
            'High priority knowledge:\n{action_context}\n\n'
            'Page title: {title}\n'
            'Page url: {url}\n\n'
            'The latest screenshot is attached as a {size}x{size} square image. '
            'When calling tap_at or drag, use 0-{size} coordinates matching this image.'
        ).format(
            prompt=prompt,
            action_context=self._agent._ai_act_context or 'none',
            title=context['title'],
            url=context['url'],
            size=REACT_IMAGE_SIZE,
        )
        return [{
            'role': 'user',
            'content': [
                {'type': 'input_text', 'text': text},
                {'type': 'input_image',
                 'image_url': _square_screenshot_data_url(context['screenshot_base64'],
                                                          context.get('screenshot_format', 'png'))},
            ],
        }]

    def _build_tools(self, yaml_flow, all_results, options):
        from agents import ToolOutputImage, ToolOutputText, function_tool

        def run_step(step):
            result = self._agent._execute_step(step, options=options)
            serialized = self._agent._serialize_result(result)
            yaml_flow.append(self._step_to_yaml_item(step))
            all_results.append({'action': step.get('action'), 'step': step, 'result': serialized})
            return [ToolOutputText(text=dumps({'action': step.get('action'), 'result': serialized},
                                              ensure_ascii=False, default=str)),
                    ToolOutputImage(image_url=self._screenshot_data_url())]

        @function_tool
        def tap(target: str) -> list:
            """Click the element described by target, e.g. 'the login button'."""
            return run_step({'action': 'aiTap', 'target': target})

        @function_tool
        def tap_at(x1: float, y1: float, x2: float, y2: float) -> list:
            """Click the element at bounding box [x1, y1, x2, y2]. Coordinates use the 0-1000
            space of the latest screenshot, which is always a 1000x1000 square image, so the
            pixel coordinates you see in the image work identically."""
            return run_step({'action': 'aiTapAt', 'bbox': [x1, y1, x2, y2], 'coord_type': 'normalized'})

        @function_tool
        def input_text(target: str, value: str, clear: bool = True) -> list:
            """Type value into the field described by target. Set clear=False to append."""
            return run_step({'action': 'aiInput', 'target': target, 'value': value, 'clear': clear})

        @function_tool
        def scroll(direction: str = 'down', pixel: int = 300, target: Optional[str] = None) -> list:
            """Scroll the page or the area described by target. direction: up/down/left/right."""
            return run_step({'action': 'aiScroll', 'target': target, 'direction': direction, 'pixel': pixel})

        @function_tool
        def keyboard_press(keys: str, target: Optional[str] = None) -> list:
            """Press a key or shortcut, e.g. 'Enter' or 'Control+a', optionally focused on target."""
            return run_step({'action': 'aiKeyboardPress', 'target': target, 'keys': keys})

        @function_tool
        def hover(target: str) -> list:
            """Hover over the element described by target."""
            return run_step({'action': 'aiHover', 'target': target})

        @function_tool
        def double_click(target: str) -> list:
            """Double click the element described by target."""
            return run_step({'action': 'aiDoubleClick', 'target': target})

        @function_tool
        def right_click(target: str) -> list:
            """Right click the element described by target."""
            return run_step({'action': 'aiRightClick', 'target': target})

        @function_tool
        def locate(target: str) -> list:
            """Locate the element described by target without interacting with it."""
            return run_step({'action': 'aiLocate', 'target': target})

        @function_tool
        def assert_condition(condition: str) -> list:
            """Assert that a statement about the current page is true. Fails the task if false."""
            return run_step({'action': 'aiAssert', 'assertion': condition})

        @function_tool
        def wait_for(condition: str, timeout: int = 10, interval: int = 1) -> list:
            """Wait until the statement about the page becomes true."""
            return run_step({'action': 'aiWaitFor', 'assertion': condition,
                             'timeout': timeout, 'interval': interval})

        @function_tool
        def query(demand: str) -> list:
            """Extract structured information from the current page."""
            return run_step({'action': 'aiQuery', 'prompt': demand})

        @function_tool
        def query_boolean(prompt: str) -> list:
            """Answer a yes/no question about the current page."""
            return run_step({'action': 'aiBoolean', 'prompt': prompt})

        @function_tool
        def query_number(prompt: str) -> list:
            """Answer with a number read from the current page."""
            return run_step({'action': 'aiNumber', 'prompt': prompt})

        @function_tool
        def query_string(prompt: str) -> list:
            """Answer with a short string read from the current page."""
            return run_step({'action': 'aiString', 'prompt': prompt})

        @function_tool
        def drag(source_bbox: list, target_bbox: list, path: str = 'curve') -> list:
            """Drag the element at source_bbox to the position of target_bbox, e.g. a
            slider onto its gap. Both are [x1, y1, x2, y2] in the 0-1000 space of the
            latest screenshot, which is always a 1000x1000 square image. The drag starts
            at the center of source_bbox and ends at the center of target_bbox.
            path: 'curve' (human-like arc, default) or 'linear'."""
            return run_step({'action': 'aiDragAt', 'source_bbox': source_bbox,
                             'target_bbox': target_bbox, 'coord_type': 'normalized',
                             'path': path})

        @function_tool
        def sleep(time_ms: int) -> list:
            """Wait for the given milliseconds, e.g. while a page loads."""
            return run_step({'action': 'Sleep', 'timeMs': time_ms})

        return [tap_at, input_text, drag, scroll]

    def _screenshot_data_url(self):
        metrics = self._adapter.get_metrics()
        normalized = normalize_screenshot_to_css_pixels(self._adapter.screenshot_base64(), metrics)
        return _square_screenshot_data_url(normalized['base64'])

    def _serialize_history(self, run_result):
        try:
            items = run_result.to_input_list()
        except Exception:
            return []
        return [_jsonable(item) for item in items]

    def _dump_debug(self, prompt, result, options):
        if not _debug_enabled(options):
            return
        save_dir = Path(_resolve_debug_dir(options.get('debug_dir')))
        save_dir.mkdir(parents=True, exist_ok=True)
        prefix = _safe_name(prompt) or 'aiact'
        path = save_dir / '{}_aiact_{}_history.json'.format(prefix, strftime('%Y%m%d_%H%M%S'))
        path.write_text(dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    def _make_cache_key(self, prompt):
        return '{}::{}'.format(self._adapter.url, prompt)

    def _step_to_yaml_item(self, step):
        action = step.get('action')
        if action == 'aiTap':
            return {'aiTap': step.get('target')}
        if action == 'aiTapAt':
            if step.get('coord_type'):
                return {'aiTapAt': {'bbox': step.get('bbox'), 'coord_type': step.get('coord_type')}}
            return {'aiTapAt': step.get('bbox')}
        if action == 'aiDragAt':
            value = {'source_bbox': step.get('source_bbox'), 'target_bbox': step.get('target_bbox')}
            if step.get('coord_type'):
                value['coord_type'] = step.get('coord_type')
            if step.get('path'):
                value['path'] = step.get('path')
            return {'aiDragAt': value}
        if action == 'aiHover':
            return {'aiHover': step.get('target')}
        if action == 'aiDoubleClick':
            return {'aiDoubleClick': step.get('target')}
        if action == 'aiRightClick':
            return {'aiRightClick': step.get('target')}
        if action == 'aiLocate':
            return {'aiLocate': step.get('target')}
        if action == 'aiInput':
            return {'aiInput': {'target': step.get('target'), 'value': step.get('value'), 'clear': step.get('clear', True)}}
        if action == 'aiKeyboardPress':
            value = {'keyName': step.get('keys')}
            if step.get('target'):
                value['locate'] = step.get('target')
            return {'aiKeyboardPress': value}
        if action == 'aiScroll':
            value = {'direction': step.get('direction', 'down'), 'pixel': step.get('pixel', 300)}
            if step.get('target'):
                value['locate'] = step.get('target')
            return {'aiScroll': value}
        if action == 'aiAssert':
            return {'aiAssert': step.get('assertion')}
        if action == 'aiWaitFor':
            return {'aiWaitFor': {'assertion': step.get('assertion'), 'timeout': step.get('timeout', 10), 'interval': step.get('interval', 1)}}
        if action in ('aiQuery', 'aiQueryImages', 'aiBoolean', 'aiNumber', 'aiString'):
            return {action: step.get('prompt')}
        if action == 'recordToReport':
            return {'recordToReport': step.get('title')}
        if action == 'Sleep':
            return {'action': 'Sleep', 'timeMs': step.get('timeMs')}
        return dict(step)


def _make_react_debug_hooks(prompt, options, model_name=''):
    """Build a RunHooks object that dumps every ReAct turn (LLM input, LLM output with
    reasoning and tool calls, tool results) to debug_dir for inspection."""
    from agents import RunHooks

    class _ReActDebugHooks(RunHooks):
        def __init__(self):
            save_dir = Path(_resolve_debug_dir(options.get('debug_dir')))
            save_dir.mkdir(parents=True, exist_ok=True)
            self._dir = save_dir
            self._stem = '{}_react_{}'.format(_safe_name(prompt) or 'aiact', strftime('%Y%m%d_%H%M%S'))
            self._turn = 0

        async def on_llm_start(self, context, agent, system_prompt, input_items):
            self._turn += 1
            self._save_latest_image(input_items)
            self._write('turn{:02d}_llm_input'.format(self._turn), {
                'system_prompt': system_prompt,
                'input': _jsonable(input_items),
            })

        async def on_llm_end(self, context, agent, response):
            output = _jsonable(getattr(response, 'output', response))
            self._write('turn{:02d}_llm_output'.format(self._turn), output)
            self._annotate_bboxes(output)

        async def on_tool_start(self, context, agent, tool):
            pass

        async def on_tool_end(self, context, agent, tool, result):
            self._write('turn{:02d}_tool_{}'.format(self._turn, getattr(tool, 'name', 'tool')),
                        _jsonable(result))

        def _write(self, suffix, data):
            path = self._dir / '{}_{}.json'.format(self._stem, suffix)
            path.write_text(dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

        def _save_latest_image(self, input_items):
            data_url = _find_last_image_url(input_items)
            if not data_url or ';base64,' not in data_url:
                return
            try:
                raw = b64decode(data_url.split(';base64,', 1)[-1])
            except Exception:
                return
            ext = 'jpg' if data_url.startswith('data:image/jpeg') else 'png'
            path = self._dir / '{}_turn{:02d}_input_image.{}'.format(self._stem, self._turn, ext)
            path.write_bytes(raw)

        def _annotate_bboxes(self, output):
            """Draw the bbox arguments of this turn's tool calls onto a copy of the image
            the model saw, so raw model output and visual context stay paired."""
            image_path = self._dir / '{}_turn{:02d}_input_image.png'.format(self._stem, self._turn)
            if not image_path.exists():
                image_path = self._dir / '{}_turn{:02d}_input_image.jpg'.format(self._stem, self._turn)
            if not image_path.exists() or not isinstance(output, list):
                return
            bboxes = []
            links = []
            for item in output:
                if not isinstance(item, dict) or item.get('type') != 'function_call':
                    continue
                args = item.get('arguments')
                try:
                    args = loads(args) if isinstance(args, str) else args
                except Exception:
                    continue
                if not isinstance(args, dict):
                    continue
                if all(k in args for k in ('x1', 'y1', 'x2', 'y2')):
                    bboxes.append(([args['x1'], args['y1'], args['x2'], args['y2']],
                                   args.get('coord_type'), (34, 197, 94, 255)))
                if isinstance(args.get('source_bbox'), list) and isinstance(args.get('target_bbox'), list):
                    bboxes.append((args['source_bbox'], 'normalized', (59, 130, 246, 255)))
                    bboxes.append((args['target_bbox'], 'normalized', (34, 197, 94, 255)))
                    links.append((args['source_bbox'], args['target_bbox']))
            if not bboxes:
                return
            try:
                from PIL import Image, ImageDraw
            except Exception:
                return
            image = Image.open(image_path).convert('RGBA')
            size = {'width': image.width, 'height': image.height}
            line_width = max(2, image.width // 600)
            cross_r = max(4, image.width // 150)
            draw = ImageDraw.Draw(image)

            def _to_box(bbox, coord_type):
                prefer_normalized = None
                if isinstance(coord_type, str):
                    hint = coord_type.strip().lower()
                    if hint in ('normalized', 'normalized_1000', '1000'):
                        prefer_normalized = True
                    elif hint in ('css', 'pixel', 'pixels', 'absolute'):
                        prefer_normalized = False
                candidates = _interpret_model_bbox({'bbox': bbox}, size, model_name=model_name,
                                                   prefer_normalized=prefer_normalized)
                return candidates[0] if candidates else None

            for bbox, coord_type, color in bboxes:
                box = _to_box(bbox, coord_type)
                if not box:
                    continue
                draw.rectangle((box['left'], box['top'], box['right'], box['bottom']),
                               outline=color, width=line_width)
                cross_x = (box['left'] + box['right']) // 2
                cross_y = (box['top'] + box['bottom']) // 2
                draw.line((cross_x - cross_r, cross_y, cross_x + cross_r, cross_y),
                          fill=(235, 64, 52, 255), width=line_width)
                draw.line((cross_x, cross_y - cross_r, cross_x, cross_y + cross_r),
                          fill=(235, 64, 52, 255), width=line_width)
            for source_bbox, target_bbox in links:
                source_box = _to_box(source_bbox, 'normalized')
                target_box = _to_box(target_bbox, 'normalized')
                if not source_box or not target_box:
                    continue
                draw.line(((source_box['left'] + source_box['right']) // 2,
                           (source_box['top'] + source_box['bottom']) // 2,
                           (target_box['left'] + target_box['right']) // 2,
                           (target_box['top'] + target_box['bottom']) // 2),
                          fill=(249, 115, 22, 255), width=line_width)
            image.save(self._dir / '{}_turn{:02d}_bbox.png'.format(self._stem, self._turn),
                       format='PNG')

    return _ReActDebugHooks()


def _debug_enabled(options):
    options = options or {}
    return bool(options.get('debug') or options.get('debug_model') or options.get('debug_request'))


def _square_screenshot_data_url(screenshot_base64, image_format='png'):
    """Resize a screenshot to a fixed square so that model pixel coordinates and 0-1000
    normalized coordinates coincide, removing coordinate-space ambiguity. Falls back to
    the original image when PIL is unavailable."""
    try:
        from PIL import Image
    except Exception:
        return 'data:image/{};base64,{}'.format(image_format, screenshot_base64)
    try:
        image = Image.open(BytesIO(b64decode(screenshot_base64))).convert('RGB')
        image = image.resize((REACT_IMAGE_SIZE, REACT_IMAGE_SIZE), Image.LANCZOS)
        buf = BytesIO()
        image.save(buf, format='JPEG', quality=88)
        return 'data:image/jpeg;base64,{}'.format(b64encode(buf.getvalue()).decode('ascii'))
    except Exception:
        return 'data:image/{};base64,{}'.format(image_format, screenshot_base64)


def _find_last_image_url(value):
    found = None
    if isinstance(value, dict):
        image_url = value.get('image_url')
        if isinstance(image_url, dict):
            image_url = image_url.get('url')
        if isinstance(image_url, str) and image_url.startswith('data:image/'):
            found = image_url
        for item in value.values():
            nested = _find_last_image_url(item)
            if nested:
                found = nested
    elif isinstance(value, (list, tuple)):
        for item in value:
            nested = _find_last_image_url(item)
            if nested:
                found = nested
    return found


def _jsonable(value):
    if isinstance(value, dict):
        return {key: ('<image>' if key == 'image_url' else _jsonable(item)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    model_dump = getattr(value, 'model_dump', None)
    if callable(model_dump):
        try:
            return _jsonable(model_dump())
        except Exception:
            pass
    return str(value)


def _safe_name(text, limit=30):
    text = sub(r'[^0-9a-zA-Z一-鿿_-]+', '_', str(text or '')).strip('_')
    return text[:limit]


_VISION_MODEL_CLASS = None


def _vision_chat_completions_model_class():
    """Return an OpenAIChatCompletionsModel subclass that keeps screenshots visible.

    Chat Completions tool messages cannot carry images: the Agents SDK silently
    drops ToolOutputImage content when converting items for that API. To keep the
    ReAct loop as "act -> observe -> act", images inside function_call_output
    items are hoisted into a user message right after the tool output.
    """
    global _VISION_MODEL_CLASS
    if _VISION_MODEL_CLASS is None:
        from agents import OpenAIChatCompletionsModel

        class VisionChatCompletionsModel(OpenAIChatCompletionsModel):
            async def get_response(self, system_instructions, input, model_settings, tools,
                                   output_schema, handoffs, tracing, previous_response_id=None,
                                   conversation_id=None, prompt=None):
                return await super().get_response(
                    system_instructions, _hoist_tool_output_images(input), model_settings,
                    tools, output_schema, handoffs, tracing,
                    previous_response_id=previous_response_id,
                    conversation_id=conversation_id, prompt=prompt)

        _VISION_MODEL_CLASS = VisionChatCompletionsModel
    return _VISION_MODEL_CLASS


def _hoist_tool_output_images(input):
    if isinstance(input, str):
        return input
    items = []
    for item in input:
        output = item.get('output') if isinstance(item, dict) else None
        if isinstance(item, dict) and item.get('type') == 'function_call_output' \
                and isinstance(output, list):
            images = [part for part in output
                      if isinstance(part, dict) and part.get('type') == 'input_image']
            if images:
                rest = [part for part in output
                        if not (isinstance(part, dict) and part.get('type') == 'input_image')]
                item = dict(item, output=rest or [{'type': 'input_text', 'text': 'Action executed.'}])
                items.append(item)
                items.append({
                    'role': 'user',
                    'content': [{'type': 'input_text',
                                 'text': 'Latest screenshot after the previous action:'}] + images,
                })
                continue
        items.append(item)
    return items
