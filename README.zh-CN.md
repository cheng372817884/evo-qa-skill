<p align="center">
  <img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/status-beta-yellow" alt="Status">
</p>

<h1 align="center">🧪 Evo QA</h1>
<p align="center"><strong>一个自我进化的 QA Agent——学习你的应用、规划测试、运行 Playwright、跨项目记忆。</strong></p>

<p align="center">
  不是测试运行器。是一个装在盒子里的、不断进化的 QA 工程师。
</p>

<p align="center">
  🌐 <a href="README.md">English</a> | <a href="README.zh-CN.md">中文</a>
</p>

<p align="center">
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-特性">特性</a> ·
  <a href="#-一次运行的产物">运行产物</a> ·
  <a href="#-文档">文档</a> ·
  <a href="#-许可证">许可证</a>
</p>

---

<p align="center">
  <video src="https://github.com/user-attachments/assets/evo-qa-intro.mp4" width="720" autoplay loop muted playsinline></video>
  <br>
  <sub>👆 Evo QA 18 秒产品介绍动画（1920×1080）</sub>
</p>

---

## 🤔 为什么需要 Evo QA？

大部分 QA 自动化的模式是 **写一次，维护一辈子**。你写测试、应用变了、测试挂了、你来修。周而复始。

Evo QA 翻转了这个模型：

- **📄 以文档和截图为食** — 给它一份规格说明，它自动规划测试
- **🤖 运行 Playwright** — 执行测试、截图留证、诊断失败原因
- **🧠 学习你的应用** — 提炼页面对象、形成对应用如何工作的洞察
- **🔁 跨项目记忆** — 携带经验前进，每个新项目都比上一个起点更高

它专为 **SDET、QA 工程师和 Agent-first 团队** 打造——一个越用越聪明的 QA 伙伴。

---

## ✨ 特性

| 能力 | 说明 |
|------|------|
| **🧠 自我进化** | 从每一次运行中学习——失败原因、模式、应用结构——并将知识应用到未来的测试 |
| **📋 测试规划** | 根据功能描述或规格说明，自动生成包含边界用例的结构化测试计划 |
| **🤖 Playwright 执行** | 运行测试、截取截图、捕获网络日志、用 AI 诊断失败原因 |
| **🗂️ 知识记忆** | 跨会话、跨项目记住应用结构、反复出现的问题和测试模式 |
| **📊 CTRF 报告** | 每次运行生成标准的 `result.ctrf.json` —— CI 友好、工具可移植 |
| **🧩 Agent 技能** | 打包为 agentskills.io 技能，兼容任何支持 Agent 的主机 |
| **📤 知识导出** | 将积累的知识导出为 mem0 JSON、CTRF 包或原始脑图转储 |
| **🔌 适配器架构** | 可插拔浏览器、执行器、信息摄取器和报告器 |

---

## 🚀 快速开始

Evo QA 是一个 **Agent 技能**，运行在兼容的 Agent 主机中（例如 CoPaw）。

### 安装技能

1. [下载最新 ZIP 包](https://github.com/cheng372817884/evo-qa-skill/archive/refs/heads/main.zip)
2. 解压后以 skill 方式导入到你的 AI 客户端即可

安装后，对你的 Agent 主机说一句：

> "测试一下 https://example.com 的登录流程"

Evo QA 就会自动：
1. 分析页面并规划测试
2. 用 Playwright 执行测试
3. 截图并捕获网络日志
4. 生成结构化的 CTRF 报告

不用写测试脚本。不用维护 CI 流水线。告诉它测什么就行。

---

## 📸 一次运行的产物

```
myapp/
├── runs/
│   └── 2026-06-20_153042/
│       ├── result.ctrf.json       ← 标准化测试报告
│       ├── evidence/
│       │   ├── step-01-login.png
│       │   ├── step-02-dashboard.png
│       │   └── network-log.har
│       └── diagnosis.md           ← AI 失败分析
├── brain/
│   ├── system/                    ← 关于应用的机械事实
│   └── business/                  ← 学习到的业务逻辑
└── plans/
    └── login-flow.md             ← 生成的测试计划
```

---

## 📚 文档

| 文件 | 用途 |
|------|------|
| [`SKILL.md`](SKILL.md) | 完整操作手册——**从这里开始** |
| [`INSTALL.md`](INSTALL.md) | 详细安装与首次运行指南 |
| [`CHANGELOG.md`](CHANGELOG.md) | 版本变更记录 |
| [`ATTRIBUTION.md`](ATTRIBUTION.md) | 开源致谢与如何署名 |
| [`references/VISION.md`](references/VISION.md) | 设计理念与长期路线图 |

---

## 🧪 测试状态

- **68 / 68 通过**（Python 3.11, Linux）
- Python 3.10+
- 默认使用 Playwright + Chromium
- 兼容 Agentskills.io v1
- 输出 CTRF v1.0 报告

---

## 📄 许可证

**Apache 2.0** — 免费使用、修改和分发。  
需保留署名——详见 [`ATTRIBUTION.md`](ATTRIBUTION.md)。

---

## 🤝 贡献指南

Evo QA 正处于早期 beta 阶段。欢迎提交 Issue、PR 和任何想法。

- **Issues**：问题报告、功能请求、疑问
- **PRs**：请先开 Issue 讨论你要改什么
- **风格**：遵循已有模式——这个项目看重清晰而非炫技

---

<p align="center">
  <sub>🧪 为相信「测试应该越来越简单，而不是越来越难」的 QA 工程师而造</sub>
</p>
