---
sidebar_position: 5
title: "内置技能目录"
description: "随 Hermes Agent 附带的内置技能目录"
---

# 内置技能目录

Hermes 附带一个内置技能库，安装时会复制到 `~/.hermes/skills/`。下方每个技能均链接至专属页面，包含完整定义、配置和用法说明。

Hermes 在执行 `hermes update` 时也会同步内置技能，但同步清单会尊重本地删除和用户编辑。如果此处列出的某个技能在你的 `~/.hermes/skills/` 目录树中缺失，它仍随 Hermes 一同发布；可通过 `hermes skills reset <name> --restore` 恢复。

如果某个技能未出现在此列表中但存在于仓库中，目录由 `website/scripts/generate-skill-docs.py` 重新生成。

## autonomous-ai-agents

| 技能 | 描述 | 路径 |
|-------|-------------|------|
| [`hermes-agent`](/user-guide/skills/bundled/autonomous-ai-agents/autonomous-ai-agents-hermes-agent) | 配置、扩展或贡献 Hermes Agent。 | `autonomous-ai-agents/hermes-agent` |

## creative

| 技能 | 描述 | 路径 |
|-------|-------------|------|
| [`ascii-art`](/user-guide/skills/bundled/creative/creative-ascii-art) | ASCII art：pyfiglet、cowsay、boxes、image-to-ascii。 | `creative/ascii-art` |

## media

| 技能 | 描述 | 路径 |
|-------|-------------|------|
| [`songsee`](/user-guide/skills/bundled/media/media-songsee) | 通过 CLI 生成音频频谱图/特征（mel、chroma、MFCC）。 | `media/songsee` |

## productivity

| 技能 | 描述 | 路径 |
|-------|-------------|------|
| [`powerpoint`](/user-guide/skills/bundled/productivity/productivity-powerpoint) | 创建、读取、编辑 .pptx 演示文稿、幻灯片、备注、模板。 | `productivity/powerpoint` |

## research

| 技能 | 描述 | 路径 |
|-------|-------------|------|
| [`arxiv`](/user-guide/skills/bundled/research/research-arxiv) | 通过关键词、作者、分类或 ID 搜索 arXiv 论文。 | `research/arxiv` |

## software-development

| 技能 | 描述 | 路径 |
|-------|-------------|------|
| [`plan`](/user-guide/skills/bundled/software-development/software-development-plan) | Plan 模式：将 Markdown 计划写入 `.hermes/plans/`，不执行。 | `software-development/plan` |
