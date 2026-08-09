# -*- coding:utf-8 -*-
"""
DrissionPage AI demo（DashScope qwen）。

配置 .env（参考 .env.example）后运行：
    python3 ai_agent_doubao_seed_2_0_pro_demo.py
"""
from os import environ
from pathlib import Path
from tempfile import gettempdir

from DrissionPage import ChromiumOptions, ChromiumPage

from demo_env import load_dotenv
import os


def prepare_qwen_env():
    load_dotenv()
    if not environ.get('OPENAI_API_KEY'):
        raise RuntimeError('请先在 .env 中设置 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL。')


def make_demo_page():
    download_dir = Path(gettempdir()) / 'drissionpage_ai_downloads'
    download_dir.mkdir(parents=True, exist_ok=True)
    opts = ChromiumOptions(read_file=False)
    opts.set_paths(download_path=str(download_dir))
    return ChromiumPage(opts)


def main():
    prepare_qwen_env()

    page = make_demo_page()
    try:
        page.get('https://chat.deepseek.com/sign_in')
        page.set.window.max()
        page.wait.doc_loaded()

        page.agent.aiTap(
            '登录按钮',
             options={'debug': True, 'debug_dir': '/tmp/dp_ai_debug'}
        )

        opened = page.agent.aiBoolean(
            '登录面板现在是否已经打开？',
            options={'refresh_context': True}
        )
        print('panel opened:', opened)

        page.agent.aiInput('账号输入框', {'value': environ.get('DEMO_PHONE', '')})
        page.agent.aiTap('提交登录按钮')

        for i in range(10):
                r = page.agent.aiAct(
            '按照指引完成弹出的验证码',
            options={
                'value': environ.get('DEMO_PHONE', ''),
                'debug': True,
                'debug_dir': '/tmp/dp_ai_debug',
            }
        )  

                opened = page.agent.aiBoolean(
                    '是否在等待用户输入手机验证码？',
                    options={'refresh_context': True}
                )
                print('通过验证码:', opened)
                if opened:
                     break
    finally:
        page.quit()


if __name__ == '__main__':
    main()
