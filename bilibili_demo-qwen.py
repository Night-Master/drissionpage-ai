# -*- coding:utf-8 -*-
"""
DrissionPage AI demo for DashScope qwen3.5-plus.

Run:
    export DASHSCOPE_API_KEY='sk-xxx'
    python3 demos/ai_agent_qwen35_plus_demo.py

Official DashScope OpenAI-compatible docs:
https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope
https://help.aliyun.com/zh/model-studio/vision
"""
from os import environ
from pathlib import Path
from tempfile import gettempdir
import time

from DrissionPage import ChromiumPage, ChromiumOptions

from demo_env import load_dotenv

import os


def prepare_qwen_env():
    load_dotenv()
    environ.setdefault('OPENAI_API_KEY', environ.get('DASHSCOPE_API_KEY', ''))
    environ.setdefault('OPENAI_BASE_URL',
                       environ.get('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'))
    environ.setdefault('OPENAI_MODEL', 'qwen3.8-max')
    if not environ.get('OPENAI_API_KEY'):
        raise RuntimeError('请先设置 DASHSCOPE_API_KEY 或 OPENAI_API_KEY。')




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
