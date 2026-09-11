# -*- coding:utf-8 -*-
"""year_picker.html 的 AI 端到端演示：用自然语言让 aiAct 把年份选到目标值。

模型自己看截图读当前年份、算差值，然后调用 wheel_at 工具发送真实滚轮事件。

配置 .env（OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL）后运行：
    .venv/bin/python demos/year_picker_ai_demo.py [目标年份，默认 1995]
"""
from os import environ
from pathlib import Path
from sys import argv

from drissionpage_ai import Chromium, ChromiumOptions

from demo_env import load_dotenv

PAGE_URL = 'file://' + (Path(__file__).parent / 'year_picker.html').resolve().as_posix()


def main():
    target = int(argv[1]) if len(argv) > 1 else 1995
    if not 1950 <= target <= 2026:
        raise SystemExit('目标年份需在 1950-2026 之间')

    load_dotenv()
    if not environ.get('OPENAI_API_KEY'):
        raise RuntimeError('请先在 .env 中设置 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL。')

    browser = Chromium(ChromiumOptions(read_file=False).auto_port())
    tab = browser.latest_tab
    try:
        tab.get(PAGE_URL)
        tab.aiAct(
            '把鼠标悬停到年份选择器上，然后用鼠标滚轮把年份调整到 {} 年，'
            '确认年份显示为目标值后结束'.format(target),
            options={'debug': True}
        )
        state = tab.run_js("""return {
            year: document.getElementById('year').textContent,
            badge: document.getElementById('hover-badge').textContent,
            wheelCount: document.getElementById('wheel-count').textContent,
        };""")
        print('最终年份: {} | hover: {} | wheel 事件数: {}'.format(
            state['year'], state['badge'], state['wheelCount']))
        assert state['year'] == str(target), '年份未到达目标值 {}，实际 {}'.format(target, state['year'])
        print('AI 选年份成功 ✔')
    finally:
        browser.quit()


if __name__ == '__main__':
    main()
