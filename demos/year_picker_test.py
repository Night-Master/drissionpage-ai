# -*- coding:utf-8 -*-
"""year_picker.html 的滚轮/悬停验证脚本。

不需要模型 API，直接用 CDP 事件验证：
1. 旧的 DOM 滚动（aiScroll 链路）对该页面无效（对照组）
2. hover_point 触发真实 mouseover
3. wheel_at_point 整格滚动（鼠标滚轮）
4. 触控板式小 delta 累积进位
5. aiWheelAt 的 css / normalized 两种坐标系

运行：
    .venv/bin/python demos/year_picker_test.py
"""
from pathlib import Path

from drissionpage_ai import Chromium, ChromiumOptions

PAGE_URL = 'file://' + (Path(__file__).parent / 'year_picker.html').resolve().as_posix()


def read_state(tab):
    return tab.run_js("""return {
        year: document.getElementById('year').textContent,
        badge: document.getElementById('hover-badge').textContent,
        wheelCount: document.getElementById('wheel-count').textContent,
    };""")


def check(label, actual, expected):
    ok = actual == expected
    print('{} [{}] 期望={} 实际={}'.format('✅' if ok else '❌', label, expected, actual))
    if not ok:
        raise AssertionError('{}: expected {!r}, got {!r}'.format(label, expected, actual))


def main():
    browser = Chromium(ChromiumOptions(read_file=False).auto_port().headless())
    tab = browser.latest_tab
    try:
        tab.get(PAGE_URL)
        agent = tab.agent
        adapter = agent._adapter

        state = read_state(tab)
        check('初始状态', (state['year'], state['badge'], state['wheelCount']),
              ('2000', 'hovered: no', '0'))

        # 1. 对照组：DOM 程序化滚动不应触发 wheel 事件（body 不可滚动，选择器只认 wheel）
        adapter.scroll(direction='down', pixel=500)
        state = read_state(tab)
        check('DOM 滚动无效（对照）', (state['year'], state['wheelCount']), ('2000', '0'))

        # 2. hover：真实 mouseover
        rect = tab.ele('#picker').rect
        cx = rect.location[0] + rect.size[0] / 2
        cy = rect.location[1] + rect.size[1] / 2
        adapter.hover_point(cx, cy)
        check('hover 触发 mouseover', read_state(tab)['badge'], 'hovered: yes')

        # 3. 鼠标滚轮整格：-4320 = 向上 36 格 -> 1964
        adapter.wheel_at_point(cx, cy, delta_y=-4320)
        check('wheel 整格 -4320', read_state(tab)['year'], '1964')

        # 4. 触控板小 delta 累积：24 次 +5 = 攒满 120 -> 1965
        for _ in range(24):
            adapter.wheel_at_point(cx, cy, delta_y=5)
        check('触控板 24x5 累积', read_state(tab)['year'], '1965')

        # 5. aiWheelAt css 坐标：+120 -> 1966
        tab.aiWheelAt(cx, cy, delta_y=120, coord_type='css')
        check('aiWheelAt(css)', read_state(tab)['year'], '1966')

        # 6. aiWheelAt 归一化 0-1000 坐标：+240 -> 1968
        metrics = adapter.get_metrics()
        vw = metrics['viewport_size']['width']
        vh = metrics['viewport_size']['height']
        tab.aiWheelAt(cx / vw * 1000, cy / vh * 1000, delta_y=240, coord_type='normalized')
        check('aiWheelAt(normalized)', read_state(tab)['year'], '1968')

        print('\n全部通过 ✔')
    finally:
        browser.quit()


if __name__ == '__main__':
    main()
