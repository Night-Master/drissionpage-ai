# -*- coding:utf-8 -*-
"""
Minimal YAML runner for DrissionPage AI.
"""
from ast import literal_eval
from os.path import exists
from re import sub
from time import sleep


class AIYamlRunner(object):
    def __init__(self, agent):
        self._agent = agent

    def run(self, yaml_script_content):
        content = self._load_content(yaml_script_content)
        data = self._parse(content)
        steps = self._normalize(data)
        variables = {}
        results = []

        if isinstance(data, dict):
            ai_context = data.get('aiActContext') or data.get('ai_action_context')
            if ai_context:
                self._agent.setAIActContext(ai_context)

        for step in steps:
            rendered = _render_templates(step, variables)
            result = self._agent._execute_step(rendered)
            saved = self._agent._serialize_result(result)
            save_as = rendered.get('save_as') or rendered.get('saveAs')
            if save_as:
                variables[str(save_as)] = saved
            results.append({
                'action': rendered.get('action'),
                'step': rendered,
                'result': saved,
            })
        return {'results': results, 'variables': variables}

    def _load_content(self, yaml_script_content):
        if isinstance(yaml_script_content, str) and exists(yaml_script_content):
            with open(yaml_script_content, 'r', encoding='utf-8') as f:
                return f.read()
        return yaml_script_content

    def _parse(self, content):
        if isinstance(content, (list, dict)):
            return content
        try:
            import yaml
        except Exception:
            yaml = None

        if yaml is not None:
            return yaml.safe_load(content)
        return _simple_yaml_load(content)

    def _normalize(self, data):
        if isinstance(data, dict):
            data = data.get('steps', [])
        if not isinstance(data, list):
            raise ValueError('runYaml() requires a top-level list or a dict with "steps".')
        return [self._normalize_step(i) for i in data]

    def _normalize_step(self, item):
        if not isinstance(item, dict):
            raise ValueError('Each YAML step must be a mapping.')
        if 'action' in item:
            return dict(item)
        if 'aiAction' in item:
            result = dict(item)
            result['action'] = 'aiAct'
            result['prompt'] = result.pop('aiAction')
            return result

        if len(item) != 1:
            raise ValueError('YAML step must contain exactly one action key or explicit "action".')

        action, value = next(iter(item.items()))
        step = {'action': action}
        if isinstance(value, dict):
            step.update(value)
            return step

        if action in ('aiTap', 'aiHover', 'aiDoubleClick', 'aiRightClick', 'aiLocate'):
            step['target'] = value
        elif action == 'Sleep':
            step['timeMs'] = value
        elif action == 'aiInput':
            raise ValueError('YAML aiInput step requires mapping form with target/value.')
        elif action == 'aiKeyboardPress':
            step['keys'] = value
        elif action == 'aiScroll':
            if isinstance(value, str):
                step['direction'] = value
        elif action in ('aiAsk', 'aiString', 'aiBoolean', 'aiNumber'):
            step['prompt'] = value
        elif action in ('aiQuery', 'aiQueryImages'):
            step['data_demand'] = value
        elif action in ('aiAssert', 'aiWaitFor'):
            step['assertion'] = value
        elif action in ('aiAct', 'ai'):
            step['prompt'] = value
            if action == 'ai':
                step['action'] = 'aiAct'
        elif action == 'evaluateJavaScript':
            step['script'] = value
        elif action == 'recordToReport':
            step['title'] = value
        else:
            step['value'] = value
        return step


def _render_templates(value, variables):
    if isinstance(value, dict):
        return {k: _render_templates(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_templates(i, variables) for i in value]
    if not isinstance(value, str):
        return value
    return sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', lambda m: str(variables.get(m.group(1), '')), value)


def _simple_yaml_load(content):
    lines = []
    for raw in str(content).splitlines():
        stripped = raw.rstrip()
        if not stripped.strip():
            continue
        if stripped.lstrip().startswith('#'):
            continue
        lines.append(stripped)
    if not lines:
        return []
    value, index = _parse_block(lines, 0, _indent_of(lines[0]))
    if index != len(lines):
        raise ValueError('Unsupported YAML structure near line: {}'.format(lines[index]))
    return value


def _parse_block(lines, index, indent):
    if lines[index][indent:indent + 2] == '- ':
        return _parse_list(lines, index, indent)
    return _parse_map(lines, index, indent)


def _parse_list(lines, index, indent):
    result = []
    while index < len(lines):
        current_indent = _indent_of(lines[index])
        if current_indent < indent:
            break
        if current_indent != indent or not lines[index][indent:].startswith('- '):
            break
        rest = lines[index][indent + 2:].strip()
        index += 1
        if not rest:
            item, index = _parse_block(lines, index, _next_indent(lines, index, indent + 2))
            result.append(item)
            continue
        if ': ' in rest or rest.endswith(':'):
            key, raw_value = _split_key_value(rest)
            item = {}
            if raw_value is None:
                nested, index = _parse_block(lines, index, _next_indent(lines, index, indent + 2))
                item[key] = nested
            else:
                item[key] = _parse_scalar(raw_value)
                while index < len(lines):
                    next_indent = _indent_of(lines[index])
                    if next_indent < indent + 2 or lines[index][next_indent:].startswith('- '):
                        break
                    if next_indent != indent + 2:
                        break
                    sub_key, sub_value = _split_key_value(lines[index].strip())
                    index += 1
                    if sub_value is None:
                        nested, index = _parse_block(lines, index, _next_indent(lines, index, indent + 4))
                        item[sub_key] = nested
                    else:
                        item[sub_key] = _parse_scalar(sub_value)
            result.append(item)
            continue
        result.append(_parse_scalar(rest))
    return result, index


def _parse_map(lines, index, indent):
    result = {}
    while index < len(lines):
        current_indent = _indent_of(lines[index])
        if current_indent < indent:
            break
        if current_indent != indent or lines[index][current_indent:].startswith('- '):
            break
        key, raw_value = _split_key_value(lines[index].strip())
        index += 1
        if raw_value is None:
            value, index = _parse_block(lines, index, _next_indent(lines, index, indent + 2))
            result[key] = value
        else:
            result[key] = _parse_scalar(raw_value)
    return result, index


def _split_key_value(text):
    if ':' not in text:
        raise ValueError('Unsupported YAML line: {}'.format(text))
    key, value = text.split(':', 1)
    key = key.strip()
    value = value.strip()
    return key, None if value == '' else value


def _parse_scalar(value):
    lower = value.lower()
    if lower == 'true':
        return True
    if lower == 'false':
        return False
    if lower in ('null', 'none'):
        return None
    if value.startswith(('"', "'")) and value.endswith(('"', "'")):
        try:
            return literal_eval(value)
        except Exception:
            return value[1:-1]
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except Exception:
        pass
    if value.startswith('[') or value.startswith('{'):
        try:
            return literal_eval(value)
        except Exception:
            return value
    return value


def _indent_of(line):
    return len(line) - len(line.lstrip(' '))


def _next_indent(lines, index, default_indent):
    if index >= len(lines):
        return default_indent
    return _indent_of(lines[index])
