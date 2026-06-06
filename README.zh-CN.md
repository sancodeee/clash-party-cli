# Clash Party CLI Windows 使用指南

[English](README.en.md) | [返回项目主页](README.md)

Clash Party CLI 是一个独立的 Windows 命令行工具。它读取 Clash Party 已有的
配置文件，并通过 Mihomo API 管理正在运行的实例，不需要修改 Clash Party 源码。

## 功能概览

- 查看 Clash Party、Mihomo、配置档案、代理、Provider、连接和规则状态。
- 切换运行模式、代理节点、TUN 和 Windows 系统代理。
- 管理配置档案、YAML 配置、备份、热重载和 CLI 自有核心进程。
- 支持交互式 REPL，以及适合脚本和 AI 工具使用的 `--json` 输出。
- 自动发现本机 Clash Party 数据目录、安装目录和 Mihomo 可执行文件。

## 环境要求

- Windows 10 或 Windows 11。
- 已安装 Clash Party，并且至少正常启动过一次。
- Python 3.10 或更高版本。
- Git。

检查环境：

```powershell
py --version
git --version
```

如果 `py` 不可用，可以将本文命令中的 `py` 替换为 `python`。

## 安装

打开 PowerShell：

```powershell
git clone https://github.com/sancodeee/clash-party-cli.git
cd clash-party-cli
py -m pip install .\agent-harness
```

验证安装：

```powershell
cli-anything-clash-party --help
cli-anything-clash-party --json version
```

如果提示找不到 `cli-anything-clash-party`，请关闭并重新打开 PowerShell。
仍然无法找到时，可以使用模块入口：

```powershell
cd clash-party-cli\agent-harness
py -m cli_anything.clash_party --help
```

## 首次使用

先启动一次 Clash Party，等待其完成初始化，然后执行以下只读命令：

```powershell
cli-anything-clash-party info
cli-anything-clash-party status
cli-anything-clash-party config validate
```

`info` 会显示自动发现的数据目录、状态目录和 Mihomo 路径。`status` 会同时显示
本地配置和正在运行的 Mihomo 后端状态。

常用全局参数必须写在子命令之前：

```text
--json             输出机器可读的 JSON
--data-dir PATH    指定 Clash Party 数据目录
--state-dir PATH   指定 CLI 状态目录
--core-path PATH   指定 Mihomo 可执行文件
--yes              自动确认危险操作
--no-start         后端不可用时不启动独立核心
```

示例：

```powershell
cli-anything-clash-party --json --no-start status
cli-anything-clash-party --data-dir "D:\ClashPartyData" info
```

## 只读检查

以下命令不会修改配置或运行状态：

```powershell
cli-anything-clash-party version
cli-anything-clash-party info
cli-anything-clash-party status
cli-anything-clash-party mode get
cli-anything-clash-party tun status
cli-anything-clash-party sysproxy status
cli-anything-clash-party profile list
cli-anything-clash-party proxy list
cli-anything-clash-party provider list proxy
cli-anything-clash-party provider list rule
cli-anything-clash-party connection list
cli-anything-clash-party rule list
cli-anything-clash-party config validate
```

列表可能很长，自动化场景建议使用 JSON：

```powershell
cli-anything-clash-party --json connection list
```

注意：配置档案元数据可能包含订阅地址。不要将未经检查的 JSON 输出公开发布。

## 模式、TUN 与系统代理

这些命令会修改状态：

```powershell
# 模式只能是 rule、global 或 direct
cli-anything-clash-party mode set rule
cli-anything-clash-party mode set global
cli-anything-clash-party mode set direct

cli-anything-clash-party tun enable
cli-anything-clash-party tun disable

cli-anything-clash-party sysproxy enable
cli-anything-clash-party sysproxy disable
```

系统代理命令当前支持 Windows 手动代理模式。修改 TUN 或系统代理可能需要管理员
权限；修改后可用对应的 `status` 命令确认结果。

## 配置档案

查看配置档案：

```powershell
cli-anything-clash-party profile list
cli-anything-clash-party profile show PROFILE_ID
```

添加本地 YAML：

```powershell
cli-anything-clash-party profile add --name "Local" --file ".\local.yaml"
```

添加远程订阅：

```powershell
cli-anything-clash-party profile add --name "Remote" --url "https://example.com/subscription"
```

选择、更新或删除配置档案：

```powershell
cli-anything-clash-party profile use PROFILE_ID
cli-anything-clash-party profile update PROFILE_ID
cli-anything-clash-party profile remove PROFILE_ID
```

`profile remove` 是破坏性操作，默认会要求确认。无人值守脚本可将全局
`--yes` 放在命令前，但使用前应先备份：

```powershell
cli-anything-clash-party --yes profile remove PROFILE_ID
```

## 代理与 Provider

查看代理组并切换节点：

```powershell
cli-anything-clash-party proxy list
cli-anything-clash-party proxy switch "Proxy" "Node Name"
```

查看和更新 Provider：

```powershell
cli-anything-clash-party provider list proxy
cli-anything-clash-party provider list rule
cli-anything-clash-party provider update proxy PROVIDER_NAME
cli-anything-clash-party provider update rule PROVIDER_NAME
```

切换代理或更新 Provider 会影响正在运行的 Mihomo 实例。

## 连接与规则

查看连接和规则：

```powershell
cli-anything-clash-party connection list
cli-anything-clash-party rule list
```

关闭连接：

```powershell
cli-anything-clash-party connection close CONNECTION_ID
cli-anything-clash-party connection close-all
```

启用或禁用规则标识：

```powershell
cli-anything-clash-party rule disable RULE_NAME
cli-anything-clash-party rule enable RULE_NAME
```

`connection close-all` 会立即中断全部活动连接。规则开关会修改配置并尝试同步
运行中的后端。

## YAML 配置

读取完整配置或点路径：

```powershell
cli-anything-clash-party config get
cli-anything-clash-party config get mode
cli-anything-clash-party config get tun.enable
```

设置 YAML 值：

```powershell
cli-anything-clash-party config set mode '"rule"'
cli-anything-clash-party config set tun.enable true
cli-anything-clash-party config set dns.nameserver '["1.1.1.1", "8.8.8.8"]'
```

`YAML_VALUE` 必须是有效的 YAML 字面量。PowerShell 中字符串值建议使用外层
单引号保留内部双引号。

导出或替换配置：

```powershell
cli-anything-clash-party config export ".\mihomo-backup.yaml"
cli-anything-clash-party config replace mihomo --file ".\mihomo.yaml"
cli-anything-clash-party config replace profile --file ".\profile.yaml"
cli-anything-clash-party config replace app --file ".\config.yaml"
```

替换前先执行备份，并在替换后验证：

```powershell
cli-anything-clash-party config validate
```

## 备份、撤销与恢复

创建和列出 ZIP 备份：

```powershell
cli-anything-clash-party backup create ".\backups\clash-party.zip"
cli-anything-clash-party backup list ".\backups"
```

恢复备份：

```powershell
cli-anything-clash-party backup restore ".\backups\clash-party.zip"
```

恢复会覆盖当前配置并要求确认。无人值守恢复：

```powershell
cli-anything-clash-party --yes backup restore ".\backups\clash-party.zip"
```

CLI 会记录受支持的配置修改，可撤销或重做最近操作：

```powershell
cli-anything-clash-party undo
cli-anything-clash-party redo
```

撤销记录保存在 CLI 状态目录中，不应替代完整备份。

## 核心、重载与日志

CLI 优先连接 Clash Party 已运行的 Mihomo。它不会停止由 Clash Party GUI
拥有的进程。

```powershell
cli-anything-clash-party core start
cli-anything-clash-party core logs --lines 200
cli-anything-clash-party core restart
cli-anything-clash-party core stop
```

`core stop` 和 `core restart` 只操作 CLI 自己启动并记录的核心。

热重载当前配置或指定文件：

```powershell
cli-anything-clash-party reload
cli-anything-clash-party reload --path ".\mihomo.yaml"
```

查看实时 Mihomo 日志：

```powershell
cli-anything-clash-party log --level info
cli-anything-clash-party log --level debug --follow
```

请求运行中的 Mihomo 自升级：

```powershell
cli-anything-clash-party core upgrade
```

升级核心会改变运行环境，执行前请确认 Clash Party 版本和核心来源兼容。

## JSON 与 REPL

将 `--json` 放在子命令前：

```powershell
cli-anything-clash-party --json status
cli-anything-clash-party --json profile list
```

成功输出格式：

```json
{"command":"version","data":{"cli":"0.1.0"},"error":null,"ok":true}
```

不要依赖人类可读输出的空格和列宽；脚本应解析 JSON 字段并检查进程退出码。

不带子命令会进入交互式 REPL：

```powershell
cli-anything-clash-party
```

在 REPL 中可以输入 `status`、`proxy list` 等相同命令；输入 `help` 查看帮助，
输入 `exit` 或按 `Ctrl+Z` 后回车退出。

## 更新与卸载

更新仓库和已安装版本：

```powershell
cd clash-party-cli
git pull
py -m pip install --upgrade .\agent-harness
```

卸载：

```powershell
py -m pip uninstall cli-anything-clash-party
```

卸载 Python 包不会删除 Clash Party 配置。CLI 的状态目录位置可通过 `info`
查看，需要时可在确认无用后手动删除。

## 故障排查

### 找不到 Clash Party 数据目录

先打开 Clash Party 一次，再运行：

```powershell
cli-anything-clash-party info
```

也可以显式指定目录：

```powershell
cli-anything-clash-party --data-dir "D:\ClashPartyData" status
```

### 无法连接 Mihomo 后端

确认 Clash Party 正在运行，并检查：

```powershell
cli-anything-clash-party --no-start status
```

如果希望 CLI 尝试启动独立核心，请去掉 `--no-start`，并确认 `info` 显示的
Mihomo 路径正确。必要时使用 `--core-path`。

### 权限或系统代理失败

以管理员身份启动 PowerShell，再执行 TUN 或系统代理命令。先使用
`sysproxy status` 检查 Clash Party 的手动代理配置是否完整。

### 配置修改后没有生效

```powershell
cli-anything-clash-party config validate
cli-anything-clash-party reload
cli-anything-clash-party status
```

如果配置损坏，可使用 `undo` 或恢复最近备份。

## 开发与测试

开发者安装：

```powershell
git clone https://github.com/sancodeee/clash-party-cli.git
cd clash-party-cli
py -m pip install -e ".\agent-harness[dev]"
```

运行完整检查：

```powershell
py -m ruff check agent-harness
py -m ruff format --check agent-harness
py -m mypy agent-harness\cli_anything\clash_party
py -m pytest agent-harness\cli_anything\clash_party\tests -v
```

测试使用临时数据目录，不会修改用户真实的 Clash Party 配置或系统代理。

## 安全说明

- 不要在 issue、日志或截图中公开订阅 URL、访问令牌或完整 JSON 配置。
- 修改配置、TUN、系统代理和运行模式前先创建备份。
- 对 `--yes`、`backup restore`、`profile remove` 和
  `connection close-all` 保持谨慎。
- CLI 仅在确认进程由自己启动后才会停止或重启该 Mihomo 进程。
- 本项目是非官方配套工具，Clash Party 与 Mihomo 分别遵循其自身许可证。
