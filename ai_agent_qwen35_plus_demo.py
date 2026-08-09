# -*- coding:utf-8 -*-
"""
DrissionPage AI demo（DashScope qwen）。

配置 .env（参考 .env.example）后运行：
    python3 ai_agent_qwen35_plus_demo.py
"""
from os import environ
from pathlib import Path
from tempfile import gettempdir
import time

from DrissionPage import ChromiumPage, ChromiumOptions

from demo_env import load_dotenv


import os

def prepare_dashscope_env():
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
    prepare_dashscope_env()


    page = make_demo_page()
    try:
        page.get('https://chat.deepseek.com/sign_in')
        page.set.window.max()
        page.wait.doc_loaded()
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
        result = page.agent.aiQuery(
      '提取验证码下方的文字描述',
      options={
          'refresh_context': True,
      }
  )
        # time.sleep(4)
        r = page.agent.aiTap(
      result,
      options={
          'value': environ.get('DEMO_PHONE', ''),
          'debug': True,
          'debug_dir': '/tmp/dp_ai_debug',
      }
  )
        
        opened = page.agent.aiBoolean(
            '登录面板现在是否已经打开？',
            options={'refresh_context': True}
        )
        print('panel opened:', opened)

        page.agent.aiInput('账号输入框', {'value': environ.get('DEMO_PHONE', '')})
        page.agent.aiTap('提交登录按钮')

        status_text = page.agent.aiString(
            '读取当前状态区域里的完整文案',
            options={'refresh_context': True}
        )
        print('status:', status_text)

        print('report entries:', len(page.agent._unstableLogContent()))
    finally:
        page.quit()


if __name__ == '__main__':
    main()
