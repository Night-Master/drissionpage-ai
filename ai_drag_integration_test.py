# -*- coding:utf-8 -*-
"""集成测试：框架版 aiDragAt（直线/曲线）+ aiAct e2e（模型自主调用 drag 工具）。

运行：
    ./.venv/bin/python ai_drag_integration_test.py            # 只跑 aiDragAt（不需要模型）
    ./.venv/bin/python ai_drag_integration_test.py --e2e      # 加跑 aiAct（需要 .env 模型配置）
"""
from sys import argv
from time import sleep

from DrissionPage import ChromiumPage, ChromiumOptions

from demo_env import load_dotenv

# 复用实验脚本里的测试页（鼠标事件驱动的滑块 + 目标框）
from cdp_drag_experiment import HTML, get_css_bbox, norm1000_to_css


def run_drag_at(page, agent, html_url, path, debug=False):
    page.get(html_url)
    sleep(0.5)
    src = get_css_bbox(page, '#handle')
    dst = get_css_bbox(page, '#drop-zone')
    src_norm = [v / src['vw'] * 1000 if i % 2 == 0 else v / src['vh'] * 1000
                for i, v in enumerate(src['bbox'])]
    dst_norm = [v / dst['vw'] * 1000 if i % 2 == 0 else v / dst['vh'] * 1000
                for i, v in enumerate(dst['bbox'])]
    # 走框架入口：0-1000 归一化 bbox -> aiDragAt -> adapter.drag_points -> CDP
    options = {'debug': True, 'debug_dir': 'debug_log'} if debug else None
    payload = agent.aiDragAt(src_norm, dst_norm, coord_type='normalized', path=path,
                             options=options)
    sleep(0.3)
    status = page.run_js('return document.getElementById("status").textContent')
    assert 'DROP SUCCESS' in status, '[{}] 拖拽未落入目标区域:\n{}'.format(path, status)
    print('[aiDragAt:{}] DROP SUCCESS'.format(path))
    if debug:
        from os.path import exists
        debug_info = payload.get('debug') or {}
        for key in ('raw_screenshot_path', 'annotated_screenshot_path', 'meta_path'):
            assert debug_info.get(key) and exists(debug_info[key]), \
                'debug 产物缺失: {} -> {}'.format(key, debug_info.get(key))
        print('[aiDragAt:{}] debug 产物: {}'.format(path, debug_info['annotated_screenshot_path']))


def run_yaml(page, agent, html_url):
    page.get(html_url)
    sleep(0.5)
    src = get_css_bbox(page, '#handle')
    dst = get_css_bbox(page, '#drop-zone')
    src_norm = [round(v / src['vw'] * 1000, 1) if i % 2 == 0 else round(v / src['vh'] * 1000, 1)
                for i, v in enumerate(src['bbox'])]
    dst_norm = [round(v / dst['vw'] * 1000, 1) if i % 2 == 0 else round(v / dst['vh'] * 1000, 1)
                for i, v in enumerate(dst['bbox'])]
    yaml_steps = {'steps': [{'aiDragAt': {'source_bbox': src_norm, 'target_bbox': dst_norm,
                                          'coord_type': 'normalized', 'path': 'linear'}}]}
    agent.runYaml(yaml_steps)
    sleep(0.3)
    status = page.run_js('return document.getElementById("status").textContent')
    assert 'DROP SUCCESS' in status, '[runYaml] 拖拽未落入目标区域:\n{}'.format(status)
    print('[runYaml:aiDragAt] DROP SUCCESS')


def run_e2e(page, agent, html_url):
    """模型通过 aiAct 自主识别滑块和目标框并调用 drag 工具。"""
    page.get(html_url)
    sleep(0.5)
    result = agent.aiAct('把蓝色滑块拖拽到绿色虚线框内',
                         options={'debug': True, 'debug_dir': 'debug_log', 'cacheable': False})
    sleep(0.5)
    status = page.run_js('return document.getElementById("status").textContent')
    actions = [r.get('action') for r in result.get('results', [])]
    print('[aiAct] actions:', actions)
    assert 'aiDragAt' in actions, 'aiAct 没有调用 drag 工具，实际动作: {}'.format(actions)
    assert 'DROP SUCCESS' in status, '[aiAct] 拖拽未落入目标区域:\n{}'.format(status)
    print('[aiAct] DROP SUCCESS (模型自主调用 drag 完成)')


def main():
    load_dotenv()
    from pathlib import Path
    html_path = Path(__file__).parent / 'debug_log' / 'cdp_drag_test_page.html'
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(HTML, encoding='utf-8')
    html_url = 'file://' + str(html_path)

    page = ChromiumPage(ChromiumOptions(read_file=False).headless(False))
    try:
        from DrissionPage import DrissionPageAgent
        agent = DrissionPageAgent(page)

        run_drag_at(page, agent, html_url, 'linear')
        run_drag_at(page, agent, html_url, 'curve', debug=True)
        run_yaml(page, agent, html_url)

        if '--e2e' in argv:
            run_e2e(page, agent, html_url)

        print('\n✅ 全部通过')
    finally:
        page.quit()


if __name__ == '__main__':
    main()
