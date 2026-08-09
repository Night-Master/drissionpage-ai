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

注意：本包与原版 `DrissionPage` 提供同名模块，二者**不可共存**，安装前请先 `pip uninstall DrissionPage`。

## AI 模型配置

支持任意 OpenAI 兼容端点（OpenAI、DashScope、ARK 等），通过环境变量配置：

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.openai.com/v1"   # 可选，使用openai兼容格式的api即可，测试火山引擎agent plan，kimi，阿里token plan均可
export OPENAI_MODEL="gpt-4o"                          # 可选，默认 gpt-4o-mini，建议使用具备视觉能力的模型,测试使用seed 2.1 tubor，kimi k3，qwen3.8max均可
```

可选调优变量：`DP_AI_TIMEOUT`（默认 90）、`DP_AI_TEMPERATURE`（默认 0）、`DP_AI_MAX_TOKENS`（默认 1200）、`DP_AI_DEBUG_DIR`（AI 调试截图/日志输出目录）。

## 快速上手

```python
from DrissionPage import ChromiumPage

page = ChromiumPage()
page.get('https://example.com')

# 自然语言点击：AI 看截图定位并点击
page.aiAct('点击"登录"按钮，在账号输入框输入 demo_user')

# 或者分步操作
page.aiInput('账号输入框', 'demo_user')
```

## 运行 demo

仓库根目录附了几个真实场景 demo（B 站登录、DeepSeek 登录等）。API key 和测试手机号通过 `.env` 文件提供：

```bash
cp .env.example .env
# 编辑 .env，填入你要用的平台 key（DASHSCOPE_API_KEY / KIMI_API_KEY / ARK_API_KEY，用哪个填哪个）
python bilibili_demo-qwen.py
```

demo 里的 `prepare_*_env()` 会通过 `demo_env.py` 读取 `.env`，并把平台 key 映射到库使用的 `OPENAI_*` 变量。`.env` 已被 gitignore，不会被提交；仓库里的 `.env.example` 是模板。

---

# 以下为 DrissionPage 原版 README

---

# ✨️ 概述

DrissionPage 是一个基于 python 的网页自动化工具。

它既能控制浏览器，也能收发数据包，还能把两者合而为一。

可兼顾浏览器自动化的便利性和 requests 的高效率。

它功能强大，内置无数人性化设计和便捷功能。

它的语法简洁而优雅，代码量少，对新手友好。

<a href="https://www.tgebrowser.com/zh" target="_blank"><img src="https://raw.githubusercontent.com/g1879/DrissionPage/refs/heads/master/img/ad.png"/></a>

---

官方网站：[https://DrissionPage.cn](https://drissionpage.cn)

项目地址：[gitee](https://gitee.com/g1879/DrissionPage)    |    [github](https://github.com/g1879/DrissionPage)     |    [gitcode](https://gitcode.com/g1879/DrissionPage) 

您的星星是对我最大的支持💖

--- 

支持系统：Windows、Linux、Mac

python 版本：3.6 及以上

支持浏览器：Chromium 内核浏览器(如 Chrome 和 Edge)，electron 应用

---

# 🛠 如何使用

**📖 使用文档：**  [点击查看](https://DrissionPage.cn)

**交流 QQ 群：**  见使用文档

![](https://drissionpage.cn/codes.png)

---

# 💡 理念

简洁而强大！

--- 

# ☀️ 特性和亮点

作者经过长期实践，踩过无数坑，总结出的经验全写到这个库里了。

## 🎇 强大的自研内核

本库采用全自研的内核，内置无数实用功能，对常用功能作了整合和优化，对比 selenium，有以下优点：

- 不基于 webdriver
- 无需为不同版本的浏览器下载不同的驱动
- 运行速度更快
- 可以跨 iframe 查找元素，无需切入切出
- 把 iframe 看作普通元素，逻辑更清晰
- 可同时操作多个标签页，无需切换
- 可以直接读取浏览器缓存保存图片，无需用 GUI 点击另存
- 可以对整个网页截图，包括视口外的部分
- 可处理非`open`状态的 shadow-root

## 🎇 亮点功能

除了以上优点，本库还内置了无数人性化设计。

- 极简的定位语法，查找元素更加容易
- 集成大量常用功能，代码更优雅，功能强大稳定
- 无处不在的等待和自动重试，使不稳定的网络变得易于控制，程序更稳定，编写更省心
- 提供强大的下载工具，操作浏览器时也能享受快捷可靠的下载功能
- 允许反复使用已经打开的浏览器，无需每次运行从头启动浏览器，调试方便
- 使用 ini 文件保存常用配置，自动调用，提供便捷的设置，远离繁杂的配置项
- 内置 lxml 作为解析引擎，解析速度成几个数量级提升
- 使用 POM 模式封装，可直接用于测试，便于扩展
- 高度集成的便利功能，从每个细节中体现
- 还有很多细节，这里不一一列举，欢迎实际使用中体验：D

--- 

# 📝 使用条款

允许任何人以个人身份使用或分发本项目源代码，但仅限于学习和合法非盈利目的。
个人或组织如未获得版权持有人授权，不得将本项目以源代码或二进制形式用于商业行为。

使用本项目需满足以下条款，如使用过程中出现违反任意一项条款的情形，授权自动失效。
- 禁止将DrissionPage应用到任何可能违反当地法律规定和道德约束的项目中
- 禁止将DrissionPage用于任何可能有损他人利益的项目中
- 禁止将DrissionPage用于攻击与骚扰行为
- 遵守Robots协议，禁止将DrissionPage用于采集法律或系统Robots协议不允许的数据

使用DrissionPage发生的一切行为均由使用人自行负责。
因使用DrissionPage进行任何行为所产生的一切纠纷及后果均与版权持有人无关，
版权持有人不承担任何使用DrissionPage带来的风险和损失。
版权持有人不对DrissionPage可能存在的缺陷导致的任何损失负任何责任。

---  
