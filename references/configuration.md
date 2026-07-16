# 首次解包与配置清单

Agent 在初始化前必须逐项向使用者展示本清单。每项都应说明检测值或默认值、用途、是否可调整，以及改变安全项可能带来的影响。不得以“保持默认”为由省略展示。

## 环境与路径

- `codex_home`：自动检测 `$CODEX_HOME`，未设置时使用 `~/.codex`。可调整。
- `active_agents_path`：默认检测为 `<codex_home>/AGENTS.md`，必须确认文件存在。可调整。
- `instance_root`：运行状态、报告和候选的独立目录，推荐 `<codex_home>/agents-md-evolution-instance`。可调整，不应放入 Skill 包内。
- `codex_executable`：自动检测 `codex` 命令的真实路径。可调整。
- `timezone`：从本机环境和系统时区数据库自动检测并展示；不得沿用打包者时区，也不要求使用者手填。检测失败时阻止创建并报告原因。

## Gmail 与报告

- `provider`：默认且当前官方路径为 `gmail`。
- `sender`：必须由当前使用者填写，并与已连接的 Gmail 账号核对；不得使用示例或打包者邮箱。
- `recipient`：必须由当前使用者填写。可以与发件人相同，但不可静默假设。
- 初始化前必须读取 Gmail 连接器 profile 并核对 `sender`。连接器未安装、未授权或账号不一致时应暂停，让使用者亲自完成授权或重连；授权完成前不得创建 Automation 或执行 onboarding 测试。
- `language`：推荐默认 `zh-CN`，邮件主题、正文、审计和安装报告均使用简体中文；模型 ID、命令和文件名可保留英文。属于可调整的呈现偏好，但修改时需同步报告模板和提示。
- `subject_prefix`：默认 `[Codex AGENTS Loop]`。可调整。
- `send_events`：默认发送 baseline、审计完成、需要修订、审计拒绝、失败和安装完成；`NO_UPDATE` 默认不发送。可调整。
- `include_complete_evaluation`：默认开启。`include_full_diff`、`include_full_original`、`include_full_candidate`：默认关闭，完整内容仍保留在本地 Run 目录；使用者可以明确开启任一邮件章节，但秘密扫描拥有更高优先级。
- `secret_scan_required`、`verify_sent`、`attachments=false`：安全底线。不得静默关闭；报告不得附带活动文件或候选文件。

## 定时与模型执行

- `schedule`：推荐默认工作日 10:00 和 17:00，由唯一的 Gmail-capable Codex Automation 执行。Automation 应使用本机最轻量可用模型和 `routine_check_reasoning_effort`（默认 `low`），只负责触发脚本和投递；可选的 Windows/macOS 登录入口只运行一次启动检查；实例锁会拒绝重叠运行。属于可调整的运行偏好，创建自动化前必须展示当地时区下的实际时间。
- `routine_check_reasoning_effort`：默认 `low`。它只控制日常 Automation 宿主会话；检测到新模型后，作者和独立复核仍严格使用优先级最高的本机可见模型以及 `author_reasoning_effort`、`reviewer_reasoning_effort`（默认均为 `max`）。
- `model_selection`：定时 Codex 任务使用确定性的 HTTP 读取方式检查 OpenAI 官方 Models 与 Changelog 页面，并把标题、状态和页面中出现的模型标识写入执行证据；这一步默认不调用任何模型，也不会使用最新强模型。随后以本机 `codex debug models` 中优先级最高的可见模型作为实际作者与复核模型。不得硬编码某个模型家族名称，也不得回退到低优先级模型。
- `official_source_check_required`：默认 `true`。如果所有官方来源都无法读取，本次检测应生成失败报告或不推进模型状态，而不是跳过官网核验继续审计。离线或内网环境可由使用者明确调整。
- `author_reasoning_effort`、`reviewer_reasoning_effort`：推荐 `max`，两者必须一致且模型目录必须声明支持；不可静默降级。可由使用者明确调整。
- `fresh_sessions=true`、`independent_reviewer=true`、`reviewer_may_edit_candidate=false`：审计完整性底线。
- `max_pending_candidates_per_model=1`：默认每个模型最多一个待审批候选。可调整，但不建议增加。
- `simulation_trigger_enabled=false`：仅测试时临时开启；模拟事件必须显著标注，不能宣称 OpenAI 真正发布了新模型。

## 审批、安装与安全

- `auto_install=false`：安全底线。定时任务不得自动覆盖全局 `AGENTS.md`。
- `approval_channel=codex`：默认只接受 Codex 任务中带 Run ID 的明确批准；邮件回复不构成批准。可扩展渠道，但必须有等价身份与范围验证。
- `approval_phrase`：默认 `批准安装 run <Run ID>`。可调整措辞，但 Run ID 必须明确。
- `active_sha_check=true`、`timestamped_backup=true`、`post_install_verification=true`：安装安全底线。
- `official_sources`：默认只使用 OpenAI 官方 Codex Models 与 Changelog 页面。可更新官方 URL，不得用非官方来源替代模型发布事实。

## 意图与个人偏好

`neutral` 配置只启用通用安全、授权、最小改动和验证规则。`michael` 配置在此基础上增加原作者 Michael 的偏好。Agent 必须逐项说明这些只是可参考的个人习惯，可保留、修改或删除：

- 默认使用完整连贯的自然段，减少逐句换行、无必要标题、列表、表格、粗体和重复总结。
- 先给结论，语气自然直接，篇幅与任务复杂度匹配。
- 除非使用者主动询问，否则不主动讨论 token、API 费用或会话成本。
- 对使用者明确认定的最终独立 Markdown 文档，按既有授权与目标目录检查 Google Drive 备份；仓库文件不自动上传。
- 从第一性原理理解真实目标，仅在关键歧义、授权或重大风险会改变结果时询问。
- 把复杂、可复用工作流放入 Skill，避免持续膨胀全局 `AGENTS.md`。

初始化后，Agent 还应扫描使用者现有 `AGENTS.md` 和提供的偏好文件，列出新发现的所有行为偏好及冲突，不得只检查上述示例。
