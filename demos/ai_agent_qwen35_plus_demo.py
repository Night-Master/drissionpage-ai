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

from DrissionPage import ChromiumPage, ChromiumOptions


HTML = '''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>DrissionPage AI Demo</title>
  <style>
    body {
      margin: 0;
      font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
      background: linear-gradient(180deg, #f7f4ea 0%, #efe7d4 100%);
      color: #1d1d1f;
    }
    .wrap {
      max-width: 980px;
      margin: 48px auto;
      display: grid;
      grid-template-columns: 260px 1fr;
      gap: 24px;
    }
    .card {
      background: rgba(255, 255, 255, 0.82);
      border: 1px solid rgba(40, 40, 40, 0.08);
      border-radius: 20px;
      box-shadow: 0 20px 50px rgba(69, 54, 26, 0.08);
      backdrop-filter: blur(10px);
    }
    .nav {
      padding: 24px;
    }
    .nav h2 {
      margin: 0 0 18px;
      font-size: 18px;
    }
    .nav button {
      width: 100%;
      margin-top: 12px;
      padding: 14px 16px;
      border: none;
      border-radius: 14px;
      text-align: left;
      font-size: 15px;
      cursor: pointer;
      background: #f3ede0;
    }
    .nav button.primary {
      background: linear-gradient(135deg, #0f766e, #155e75);
      color: #fff;
      font-weight: 700;
    }
    .main {
      padding: 28px;
    }
    .hero {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }
    .hero h1 {
      margin: 0;
      font-size: 32px;
    }
    .hero p {
      margin: 10px 0 0;
      color: #5f5c53;
      line-height: 1.7;
    }
    .status {
      margin-top: 20px;
      padding: 12px 14px;
      border-radius: 12px;
      background: #f4f0e7;
      color: #6b5d39;
      font-size: 14px;
    }
    .panel {
      margin-top: 24px;
      display: none;
      padding: 20px;
      border-radius: 16px;
      background: #fffdfa;
      border: 1px solid #eee2c7;
    }
    .panel.visible {
      display: block;
    }
    label {
      display: block;
      margin: 12px 0 6px;
      font-size: 14px;
    }
    input {
      width: 100%;
      box-sizing: border-box;
      padding: 12px;
      border-radius: 12px;
      border: 1px solid #d9cdb2;
      font-size: 15px;
      background: #fff;
    }
    .submit {
      margin-top: 16px;
      padding: 12px 16px;
      border: none;
      border-radius: 12px;
      background: #8b5e34;
      color: #fff;
      cursor: pointer;
      font-weight: 700;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <aside class="card nav">
      <h2>控制台</h2>
      <button>仪表盘</button>
      <button>订单中心</button>
      <button class="primary" id="login-entry">立即登录并继续</button>
      <button>帮助文档</button>
    </aside>
    <main class="card main">
      <section class="hero">
        <div>
          <h1>AI Agent 视觉定位演示</h1>
          <p>这个页面专门给 DrissionPage 的 page.agent.aiLocate() 和 aiTap() 做回归验证。</p>
        </div>
      </section>
      <div class="status" id="status">当前状态：尚未登录</div>
      <div class="panel" id="login-panel">
        <label for="username">账号</label>
        <input id="username" placeholder="请输入账号">
        <label for="password">密码</label>
        <input id="password" type="password" placeholder="请输入密码">
        <button class="submit" id="submit-btn">提交登录</button>
      </div>
    </main>
  </div>
  <script>
    const entry = document.getElementById('login-entry');
    const panel = document.getElementById('login-panel');
    const status = document.getElementById('status');
    const submit = document.getElementById('submit-btn');

    entry.addEventListener('click', function() {
      panel.classList.add('visible');
      status.textContent = '当前状态：登录面板已打开';
    });

    submit.addEventListener('click', function() {
      const username = document.getElementById('username').value || '未填写';
      status.textContent = '当前状态：已提交登录，账号=' + username;
    });
  </script>
</body>
</html>
'''


def prepare_dashscope_env():
    environ.setdefault('OPENAI_API_KEY', environ.get('DASHSCOPE_API_KEY', ''))
    environ.setdefault('OPENAI_BASE_URL',
                       environ.get('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'))
    environ.setdefault('OPENAI_MODEL', 'qwen3.5-plus')
    if not environ.get('OPENAI_API_KEY'):
        raise RuntimeError('请先设置 DASHSCOPE_API_KEY 或 OPENAI_API_KEY。')


def write_demo_html():
    path = Path(gettempdir()) / 'drissionpage_ai_agent_demo.html'
    path.write_text(HTML, encoding='utf-8')
    return path


def make_demo_page():
    download_dir = Path(gettempdir()) / 'drissionpage_ai_downloads'
    download_dir.mkdir(parents=True, exist_ok=True)
    opts = ChromiumOptions(read_file=False)
    opts.set_paths(download_path=str(download_dir))
    return ChromiumPage(opts)


def main():
    prepare_dashscope_env()
    html_path = write_demo_html()

    page = make_demo_page()
    try:
        page.get(html_path.as_uri())
        page.set.window.max()
        page.wait.doc_loaded()

        page.agent.setAIActContext(
            '这是一个中文后台页面。主目标是打开登录面板，再确认登录状态文案变化。'
        )

        locate_result = page.agent.aiLocate(
            '左侧用于打开登录面板的主按钮',
        )
        print('aiLocate result:')
        print(locate_result.as_dict())

        page.agent.aiTap(
            '左侧用于打开登录面板的主按钮',
        )

        opened = page.agent.aiBoolean(
            '登录面板现在是否已经打开？',
            options={'refresh_context': True}
        )
        print('panel opened:', opened)

        page.agent.aiInput('账号输入框', {'value': 'demo_user'})
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
