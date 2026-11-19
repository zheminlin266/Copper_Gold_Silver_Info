# 周报生成与发布

Windows 计划任务每周一北京时间 08:00 启动。报告覆盖前一周周一 00:00 至本周周一 00:00 前。错过触发时以最近应执行的周一为准。报告由周期周一标识，例如 2026 年 11 月 9–15 日对应 data/weekly/2026-11-09.json。

任务使用独立、与远程 main 同步的分离工作区，并在启动时获取进程锁。Codex 按每次保存的 [周报采集提示](Weekly_Task_Prompt.md) 输出草稿，包装脚本校验并写入当周报告和可核验的 SMM TC。已发布的周报只续验。生成或发布中断后检查 .runtime/weekly/ 周目录内的状态及草稿，再以原周一重新运行。失败原因和 TC 状态保存在该次运行记录中。数据通过校验、测试和构建后提交至 main，验证实际 main SHA 的 push CI、周报首页与单期、历史日报归档、TC 页和相应来源 href。

## 首次切换

先核对 11 月 9–15 日样稿对应的 PR CI 和 Vercel Preview，再在实际 main 的 CI 和正式站重复验收。正式站浏览器检查覆盖 1440、800、390 像素视口、导航和日期检索、TC 菜单与图表。

在安装过依赖的专用分离工作区运行。

```powershell
$python = Join-Path $env:USERPROFILE '.codex\tools\browser-use\Scripts\python.exe'
& $python -B scripts/run_scheduled_weekly.py --verify-only --week-start 2026-11-09
./scripts/register_weekly_task.ps1 -VerifiedWeek 2026-11-09 -CodexSandbox danger-full-access -WhatIf
./scripts/register_weekly_task.ps1 -VerifiedWeek 2026-11-09 -CodexSandbox danger-full-access
```

注册脚本复核当周验收记录和报告、TC 的哈希，确认日报进程已退出，停用原 Windows 任务后启用新任务。切换失败时恢复原任务。电脑需开机、联网并已登录，计划使用 Windows China Standard Time。

## 运行排查

```powershell
Get-ScheduledTask -TaskName 'CopperGoldSilverInfo-Weekly-Codex'
Get-ScheduledTaskInfo -TaskName 'CopperGoldSilverInfo-Weekly-Codex'
& $python -B scripts/run_scheduled_weekly.py --dry-run
```

每周任务只提交当周 JSON 与可核验的单条 TC 更新。历史数据为日报归档的输入。核对外部库存及 TC 导航时只检查站内链接的目标地址。
