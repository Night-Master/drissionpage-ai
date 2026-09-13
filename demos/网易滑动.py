# -*- coding:utf-8 -*-
"""
DrissionPage AI demo（DashScope qwen）。

配置 .env（参考 .env.example）后运行：
    python3 deepseek-login.py
"""
from os import environ
from pathlib import Path
from tempfile import gettempdir

from drissionpage_ai import Chromium, ChromiumOptions

from demo_env import load_dotenv
import os


def prepare_qwen_env():
    load_dotenv()
    if not environ.get('OPENAI_API_KEY'):
        raise RuntimeError('请先在 .env 中设置 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL。')


DEBUG_DIR = str(Path(__file__).parent / 'debug_log')


def make_demo_page():
    download_dir = Path(gettempdir()) / 'drissionpage_ai_downloads'
    download_dir.mkdir(parents=True, exist_ok=True)
    opts = ChromiumOptions(read_file=False).auto_port()
    opts.set_paths(download_path=str(download_dir))
    return Chromium(opts).latest_tab


def main():
    prepare_qwen_env()

    page = make_demo_page()
    try:
        page.get('https://dun.163.com/trial/word-group')
        page.set.window.max()
        page.wait.doc_loaded()
        # page.agent.aiHover("验证码滑块")
        for i in range(10):
                r = page.agent.aiAct(
            '先点进去嵌入式验证码的菜单栏，完成语义选词的嵌入式验证码',
            options={
                'debug': True
                ,'preview_actions': True
            }
        )  

                opened = page.agent.aiBoolean(
                    '是否过了验证码',
                    options={'refresh_context': True}
                )
                print('通过验证码:', opened)
                if opened:
                     break
    finally:
        page.quit()


if __name__ == '__main__':
    main()
