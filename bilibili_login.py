# -*- coding:utf-8 -*-
"""
DrissionPage AI demo（kimi k3）。

配置 .env（参考 .env.example）后运行：
    python3 bilibili_demo-kimi.py
"""
from os import environ
from pathlib import Path
from tempfile import gettempdir
import time

from DrissionPage import ChromiumPage, ChromiumOptions

from demo_env import load_dotenv

import os


def prepare_kimi_env():
    load_dotenv()
    # kimi k3 只接受 temperature=1，库默认是 0，会被 400 拒绝
    environ.setdefault('DP_AI_TEMPERATURE', '1')
    if not environ.get('OPENAI_API_KEY'):
        raise RuntimeError('请先在 .env 中设置 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL。')




def make_demo_page():
    download_dir = Path(gettempdir()) / 'drissionpage_ai_downloads'
    download_dir.mkdir(parents=True, exist_ok=True)
    opts = ChromiumOptions(read_file=False)
    opts.set_paths(download_path=str(download_dir))
    return ChromiumPage(opts)


def main():
    prepare_kimi_env()

    page = make_demo_page()
    try:
        page.get('https://www.bilibili.com')
        page.set.window.max()
        page.wait.doc_loaded()

        r = page.agent.aiTap(
      '点击登录',
      options={
          'debug': True,
          'debug_dir': '/tmp/dp_ai_debug',
      }
  )
        time.sleep(2)
        r = page.agent.aiTap(
      '手机验证码登录',
      options={
          'value': environ.get('DEMO_PHONE', ''),
          'debug': True,
          'debug_dir': '/tmp/dp_ai_debug',
      }
  )
        time.sleep(2)
        r = page.agent.aiInput(
      '手机号输入框',
      options={
          'value': environ.get('DEMO_PHONE', ''),
          'debug': True,
          'debug_dir': '/tmp/dp_ai_debug',
      }
  )
        r = page.agent.aiTap(
      '发送验证码',
      options={
          'value': environ.get('DEMO_PHONE', ''),
          'debug': True,
          'debug_dir': '/tmp/dp_ai_debug',
      }
  )
        time.sleep(4)
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
