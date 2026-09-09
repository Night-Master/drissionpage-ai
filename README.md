# drissionpage-ai

> ⚠️ 本项目**基于 [DrissionPage](https://github.com/g1879/DrissionPage)（作者 g1879）二次开发**，在原版基础上新增了 AI 能力。版权归原作者所有，本项目遵循原版 LICENSE（仅限个人学习与非盈利用途，商用需获得 g1879 授权）。

在 DrissionPage 之上提供自然语言驱动的浏览器自动化：

- **`aiLocate(target)`** — 用自然语言描述定位元素（视觉模型 + 截图）
- **`aiTap(target)` / `aiInput(target, text)` / `aiTapAt(bbox)`** — AI 定位后直接操作，支持模型原生坐标点击
- **`aiQuery(prompt)` / `aiAsk(prompt)`** — 用自然语言从页面提取结构化数据
- **`aiAct(prompt, options={'max_turns': 20})`** — ReAct 循环智能体，自主观察截图、点击、输入，完成多步任务

## 安装

```bash
pip install drissionpage-ai
```

本包是 DrissionPage 的 AI 插件，会自动安装官方 `DrissionPage`（>=4.1.1）作为依赖，二者可以共存。`import drissionpage_ai` 后，DrissionPage 的所有页面对象（`ChromiumTab` 等）都会获得 `agent` 属性和 `ai*` 系列方法。

## AI 模型配置

支持任意 OpenAI 兼容端点（OpenAI、DashScope、ARK 等），通过环境变量配置：

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"   # 可选，使用openai兼容格式的api即可，测试火山引擎agent plan，kimi，阿里token plan均可
export OPENAI_MODEL="gpt-4o"                          # 可选，默认 gpt-4o-mini，建议使用具备视觉能力的模型,测试使用seed 2.1 tubor，kimi k3，qwen3.8max均可
```

可选调优变量：`DP_AI_TIMEOUT`（默认 90）、`DP_AI_TEMPERATURE`（默认 0）、`DP_AI_MAX_TOKENS`（默认 1200）、`DP_AI_DEBUG_DIR`（AI 调试截图/日志输出目录；未设置时默认输出到调用脚本所在目录下的 `debug_log/` 文件夹，找不到脚本文件时回退到系统临时目录）。开启 debug 后建议把 `debug_log/` 加入 `.gitignore`，避免误提交截图和请求日志。

## 快速上手

```python
import drissionpage_ai  # import 即为页面对象启用 ai* 方法
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://example.com')

# 自然语言点击：AI 看截图定位并点击
tab.aiAct('点击"登录"按钮，在账号输入框输入 demo_user')

# 或者分步操作
tab.aiInput('账号输入框', 'demo_user')
```

## 运行 demo

仓库根目录附了几个真实场景 demo（B 站登录、DeepSeek 登录等）。模型配置通过 `.env` 文件提供：

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
# （.env.example 注释里有 qwen / kimi / seed 三个平台的参考配置）
python bilibili_login.py
```

demo 里的 `prepare_*_env()` 通过 `demo_env.py` 把 `.env` 加载为环境变量。`.env` 已被 gitignore，不会被提交；仓库里的 `.env.example` 是模板。

---

DrissionPage 本身的用法见官方文档：[https://drissionpage.cn](https://drissionpage.cn)（注意：官方自 4.1 起推荐 `Chromium().latest_tab` 写法，`ChromiumPage`/`WebPage` 将在 5.0 移除，本插件已适配新写法）。

