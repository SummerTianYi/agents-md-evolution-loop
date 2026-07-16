# AGENTS 演进

`agents-evolve` 是一个仅面向 Codex 的可复用 Skill。它会用轻量、确定性的方式读取 OpenAI 官方模型页面和更新日志，再以本机 `codex debug models` 中真实可调用的模型目录为准检测新 Codex 模型；只有确认需要审计时，才以最高推理强度审计全局 `AGENTS.md`，再由同一模型的独立会话复核候选内容，最后生成可供人工批准的中文报告。它绝不会因为定时检查而自动替换你的 `AGENTS.md`。

## 它解决什么问题

Codex 模型更新后，新模型可能发现既有全局规则中的表达歧义、边界缺失或与最新能力不匹配之处。本 Skill 将这件事变成可追溯的闭环：轻量检查官方来源、确认本机可用模型、生成候选、独立复核、完整对比、人工批准、带备份安装。模型是否“发布并可用”由本机 `codex debug models` 中真实可见且优先级最高的目录决定；官方模型与更新日志页面只用于核验发布背景，不会代替本机可用性判断，也不会调用最新强模型来做简单抓取。

## 前置条件

- Python 3.10 或更高版本。
- 已在本机登录的 Codex CLI；如未登录，请先运行 `codex login`。
- 一个本机全局 `AGENTS.md`。
- 若要接收邮件报告：已在 Codex 中连接并授权的 Gmail。Gmail 是当前默认且唯一支持的投递方式。

支持 macOS 与 Windows。两端共享相同的审计流程；Skill 会分别处理 Codex CLI 定位、系统时区与启动项差异。

## 第一次使用

将仓库下载到本机后，把其目录作为 Skill 提供给 Codex，并让 Codex 使用 `$agents-evolve` 初始化。Codex 会先读取 [`SKILL.md`](SKILL.md) 和 [`references/configuration.md`](references/configuration.md)，检测本机环境，再逐项展示所有设置、默认值、安全级别及其来源。

你需要确认或填写以下内容：

1. 要审计的全局 `AGENTS.md` 路径。
2. Gmail 发件与收件地址，并确认 Codex 已连接对应 Gmail 账号。
3. 运行实例目录；默认建议放在 Codex 主目录下的独立实例文件夹。
4. 偏好配置：中性配置，或作者 Michael 的可选个人偏好配置。后者会逐项说明，绝不会被当作通用规则。
5. 执行时间：默认工作日 10:00 与 17:00。本机时区会自动检测，只有你要求时才需要覆盖。
6. 是否安装本地登录检查入口；它在 Windows 登录或 macOS LaunchAgent 加载时只运行一次、生成待投递请求后退出，不发送邮件。

也可以先手动检查环境：

```bash
python scripts/init_instance.py inspect
```

macOS 上若本机惯例为 `python3`，请用 `python3` 替代上面的 `python`。

确认设置后，Codex 会运行类似下面的初始化命令；首次执行只做安全演练，不会安装候选：

```bash
python scripts/bootstrap.py --root <实例目录> --gmail-sender <发件地址> --gmail-recipient <收件地址> --preference-profile neutral --install-local-audit-daemon --run-once
```

随后，Codex 会基于生成的 `<实例目录>/automation-prompt.md` 创建一个具备 Gmail 能力的定时任务。该任务使用本机最轻量可用模型和 `low` 推理强度，只负责日常触发、去重和投递；检测到变化后，脚本才启动最高优先级模型的 `max` 作者与独立复核会话。它是工作日 10:00 与 17:00 检查的唯一所有者；登录入口只做一次启动检查。实例锁会让重叠调用返回 `busy`，避免两个 Run 竞争同一状态。只有 Codex 定时任务可发送报告：它会先在 Gmail“已发送”中按唯一主题和 Run ID 去重，再发送完整 Markdown 正文，并再次核验“已发送”记录。普通 Python 脚本不会模拟或绕过 Gmail 授权。

## 每次检查会做什么

在设定时间，定时任务先用普通 HTTP 读取官方来源并记录证据，再读取本机 Codex 模型目录。若没有新模型，返回 `NO_UPDATE`，不创建或发送报告；若发现新模型，则使用该模型和最高推理强度分别启动作者与独立复核会话。两者均为全新会话，且复核前后会校验候选文件的校验和，防止复核过程擅自改写候选。

报告为简体中文。正文默认包含结构化 JSON 风险与审批建议、完整审计结论和明确的批准方式；完整 diff、修改前全文和修改后全文保留在本地 Run 目录，使用者可明确开启后再随邮件发送。若扫描发现可能的秘密，报告会按安全规则省略相关全文与 diff，绝不绕过扫描。

## 批准与安装

邮件回复不是批准。只有你在 Codex 任务中明确说出要批准的 Run ID，Codex 才会执行安装。例如：

```text
批准安装 run 20260715T045330Z-gpt-5-6-sol
```

安装前会重新核验当前 `AGENTS.md` 的 SHA-256；若文件已被其他操作改动，候选会失效而不会覆盖新内容。安装时会创建带时间戳的备份，替换后再验证最终文件与校验和，并生成中文安装报告。

## 安全边界

- `auto_install` 固定为 `false`；定时任务不会自动安装。
- 不会打包或上传运行状态、报告、备份、地址、凭据、绝对路径或你的 `AGENTS.md` 正文。
- 不会降低命名 Run 批准、校验和验证、备份、秘密扫描、收件人限制、Gmail 已发送核验或推理强度要求。
- 本地登录检查入口是可选项，只执行一次并写入可审计的投递请求；它从不发送邮件，也不会声称邮件已送达。

## 验证

仓库包含无需 Codex 账号即可运行的离线测试：

```bash
python -m unittest discover -s tests -v
```

GitHub Actions 会在 Windows 和 macOS 上运行这些测试。真实的 `codex exec` 审计需要已登录的 Codex 账号和本机模型目录，因此属于本机集成验证。
