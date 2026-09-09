# -*- coding:utf-8 -*-
"""真实易盾滑块验证码 e2e：natural 方案的 aiAct ReAct 循环一次通关验证。

运行：
    ./.venv/bin/python yidun_aiact_e2e.py
"""
from pathlib import Path
from time import sleep

from drissionpage_ai import Chromium, ChromiumOptions

from demo_env import load_dotenv
from drag_no_square_experiment import prepare_captcha, URL

DEBUG_DIR = str(Path(__file__).parent / 'debug_log')


def main():
    load_dotenv()
    page = Chromium(ChromiumOptions(read_file=False)).latest_tab
    try:
        page.get(URL)
        page.set.window.max()
        page.wait.doc_loaded()
        sleep(3)
        prepare_captcha(page)

        from drissionpage_ai import DrissionPageAgent
        agent = DrissionPageAgent(page)
        result = agent.aiAct(
            '完成滑块拼图验证码：把验证条上的滑块拖拽到拼图的缺口位置',
            options={'debug': True, 'debug_dir': DEBUG_DIR, 'cacheable': False})
        sleep(1.5)
        actions = [r.get('action') for r in result.get('results', [])]
        print('actions:', actions)

        solved = agent.aiBoolean('滑块拼图验证码是否已经通过（显示成功/对勾）',
                                 options={'refresh_context': True})
        print('验证码通过:', solved)
        assert solved, '验证码未通过'
        print('\n✅ 真实易盾验证码 e2e 通过')
    finally:
        page.quit()


if __name__ == '__main__':
    main()
