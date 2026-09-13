# -*- coding:utf-8 -*-
"""year_dropdown.html 的 AI 端到端演示：点击打开下拉框，再用滚轮滚动列表并点选目标年份。

模型需要自己完成三步：点击选择框展开列表 -> 把滚轮悬停在列表区域上滚动 -> 点击目标年份行。
页面本身不可滚动，列表是 overflow:auto 的内滚动区域，只有真实 wheel 事件能滚动它。

配置 .env（OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL）后运行：
    .venv/bin/python demos/year_dropdown_ai_demo.py [目标年份，默认 1987]
"""
from os import environ
from pathlib import Path
from sys import argv

from drissionpage_ai import Chromium, ChromiumOptions

from demo_env import load_dotenv

PAGE_URL = 'file://' + (Path(__file__).parent / 'year_dropdown.html').resolve().as_posix()


def main():
    target = int(argv[1]) if len(argv) > 1 else 1987
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
            '这是一个年份选择器。点击选择框展开下拉列表，列表显示的年份范围有限，'
            '需要把鼠标悬停在下拉列表上用滚轮滚动来浏览更多年份，'
            '找到 {} 年后点击它，确认选择框最终显示 {} 后结束'.format(target, target),
            options={'debug': True,'preview_actions': True}
        )
        state = tab.run_js("""return {
            year: document.getElementById('current-year').textContent,
            dropdownHidden: document.getElementById('dropdown').hidden,
            wheelCount: document.getElementById('wheel-count').textContent,
        };""")
        print('最终年份: {} | 下拉框已关闭: {} | 列表 wheel 事件数: {}'.format(
            state['year'], state['dropdownHidden'], state['wheelCount']))
        assert state['year'] == str(target), '年份未到达目标值 {}，实际 {}'.format(target, state['year'])
        print('AI 下拉选年份成功 ✔')
    finally:
        browser.quit()


if __name__ == '__main__':
    main()
