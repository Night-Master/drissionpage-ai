# -*- coding:utf-8 -*-
"""Smoke demo: aiAct ReAct loop with coordinate-based tap_at, on a local page.

配置 .env（参考 .env.example）后运行：
    ./.venv/bin/python ai_act_react_smoke_demo.py

Debug artifacts (per-turn ReAct dumps, annotated screenshots) go to ./debug_log.
"""
from os import environ
from pathlib import Path
from tempfile import gettempdir

from drissionpage_ai import Chromium, ChromiumOptions

from demo_env import load_dotenv

DEBUG_DIR = str(Path(__file__).parent / 'debug_log')


def prepare_env():
    load_dotenv()
    if not environ.get('OPENAI_API_KEY'):
        raise RuntimeError('请先在 .env 中设置 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL。')


def make_demo_page():
    download_dir = Path(gettempdir()) / 'drissionpage_ai_downloads'
    download_dir.mkdir(parents=True, exist_ok=True)
    opts = ChromiumOptions(read_file=False)
    opts.set_paths(download_path=str(download_dir))
    return Chromium(opts).latest_tab


prepare_env()

HTML = '''<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>aiAct smoke</title></head>
<body>
  <div style="display:flex;gap:24px;max-width:900px;margin:40px auto;font-family:sans-serif;">
    <aside style="width:240px;padding:20px;border:1px solid #ddd;border-radius:12px;">
      <h2>控制台</h2>
      <button style="display:block;width:100%;margin-top:10px;padding:12px;">仪表盘</button>
      <button id="login-entry" style="display:block;width:100%;margin-top:10px;padding:12px;background:#155e75;color:#fff;border:none;border-radius:8px;">立即登录并继续</button>
    </aside>
    <main style="flex:1;padding:20px;border:1px solid #ddd;border-radius:12px;">
      <h1>AI Agent 视觉定位演示</h1>
      <div id="status" style="margin-top:16px;padding:10px;background:#f4f0e7;">当前状态：尚未登录</div>
      <div id="login-panel" style="display:none;margin-top:20px;padding:16px;border:1px solid #eee2c7;">
        <label>账号</label><input id="username" placeholder="请输入账号" style="display:block;margin:8px 0;padding:8px;">
        <button id="submit-btn" style="padding:10px 16px;background:#8b5e34;color:#fff;border:none;border-radius:8px;">提交登录</button>
      </div>
    </main>
  </div>
  <script>
    document.getElementById('login-entry').addEventListener('click', function() {
      document.getElementById('login-panel').style.display = 'block';
      document.getElementById('status').textContent = '当前状态：登录面板已打开';
    });
  </script>
</body>
</html>
'''

html_path = Path(gettempdir()) / 'dp_ai_act_smoke.html'
html_path.write_text(HTML, encoding='utf-8')

page = make_demo_page()
try:
    page.get('file://{}'.format(html_path))
    page.wait.doc_loaded()
    result = page.agent.aiAct(
        '点击"立即登录并继续"按钮打开登录面板，然后在账号输入框输入 demo_user',
        options={'max_turns': 8, 'debug': True, 'debug_dir': DEBUG_DIR, 'force_replan': True},
    )
    print('yaml_flow:', result['yaml_flow'])
    print('final_output:', result['final_output'])
finally:
    page.quit()
