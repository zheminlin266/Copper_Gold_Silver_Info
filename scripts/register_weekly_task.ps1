[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')]
    [string]$VerifiedWeek,
    [ValidateSet('workspace-write', 'danger-full-access')]
    [string]$CodexSandbox = 'workspace-write'
)

$ErrorActionPreference = 'Stop'
$weeklyName = 'CopperGoldSilverInfo-Weekly-Codex'
$dailyName = 'CopperGoldSilverInfo-Daily-Codex'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$commonGitDir = git -C $root rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0) { throw 'Unable to locate the shared Git directory.' }
$dailyRoot = Split-Path -Parent (Resolve-Path -LiteralPath $commonGitDir).Path
if ($root -eq $dailyRoot -or (Get-TimeZone).Id -ne 'China Standard Time') {
    throw 'Use the dedicated weekly checkout and China Standard Time.'
}
$branch = git -C $root rev-parse --abbrev-ref HEAD
if ($LASTEXITCODE -ne 0 -or $branch -ne 'HEAD') { throw 'The weekly checkout must be detached.' }

$receipt = Get-Content -LiteralPath (Join-Path $root ".runtime/weekly/$VerifiedWeek/state.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$localSha = git -C $root rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Unable to read the weekly checkout commit.' }
$remoteRef = git -C $root ls-remote --exit-code origin refs/heads/main
if ($LASTEXITCODE -ne 0) { throw 'Unable to read remote main.' }
$remoteSha = ($remoteRef -split '\s+')[0]
$reportHash = (Get-FileHash -LiteralPath (Join-Path $root "data/weekly/$VerifiedWeek.json") -Algorithm SHA256).Hash
$tcHash = (Get-FileHash -LiteralPath (Join-Path $root 'data/smm_copper_concentrate_index_2026.csv') -Algorithm SHA256).Hash
if ($receipt.status -ne 'success' -or $receipt.week_start -ne $VerifiedWeek -or
    $receipt.verified_main_sha -ne $localSha -or $remoteSha -ne $localSha -or
    $receipt.report_sha256 -ne $reportHash -or $receipt.tc_sha256 -ne $tcHash) {
    throw 'The verified weekly report, TC data and successful main publication must match before switching.'
}

$python = Join-Path $env:USERPROFILE '.codex\tools\browser-use\Scripts\python.exe'
$wrapper = Join-Path $root 'scripts\run_scheduled_weekly.py'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
foreach ($required in @($python, $wrapper, $powershell, (Join-Path $root 'Weekly_Task_Prompt.md'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing $required" }
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$daily = Get-ScheduledTask -TaskName $dailyName -TaskPath '\'
$dailySid = [System.Security.Principal.NTAccount]::new($daily.Principal.UserId).Translate([System.Security.Principal.SecurityIdentifier]).Value
$dailyRuntime = Join-Path $dailyRoot '.runtime'
$dailyCheckout = (Resolve-Path -LiteralPath (Join-Path $dailyRuntime 'codex-daily-checkout')).Path
$dailyLauncher = (Resolve-Path -LiteralPath (Join-Path $dailyRuntime 'codex-daily-launch.ps1')).Path
$launcherArgument = '(?:^|\s)-File\s+(?:"{0}"|{0})(?:\s|$)' -f ([regex]::Escape($dailyLauncher))
if ($dailySid -ne $identity.User.Value -or $daily.Actions.Count -ne 1 -or
    $daily.Actions[0].Execute -ne $powershell -or
    (Resolve-Path -LiteralPath $daily.Actions[0].WorkingDirectory).Path -ne $dailyCheckout -or
    $daily.Actions[0].Arguments -notmatch $launcherArgument -or
    -not (Select-String -LiteralPath $dailyLauncher -Pattern 'run_scheduled_daily\.py' -Quiet) -or
    [string]$daily.State -notin @('Ready', 'Disabled')) {
    throw 'The daily task must belong to this project and must have finished running before cutover.'
}

$arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -Command "& ''{0}'' -B ''{1}'' --codex-sandbox {2}; exit $LASTEXITCODE"' -f $python.Replace("'", "''"), $wrapper.Replace("'", "''"), $CodexSandbox
$action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments -WorkingDirectory $root
$nextMonday = [DateTime]::Today.AddHours(8)
while ($nextMonday.DayOfWeek -ne 'Monday' -or $nextMonday -le (Get-Date)) { $nextMonday = $nextMonday.AddDays(1) }
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday -At $nextMonday
$settings = New-ScheduledTaskSettingsSet -Disable -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 8) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
$definition = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description 'Collect and publish the prior Beijing Monday-Sunday copper report and weekly SMM TC at Monday 08:00.'

$existing = Get-ScheduledTask -TaskName $weeklyName -TaskPath '\' -ErrorAction SilentlyContinue
if ($existing -and ($existing.Actions.Count -ne 1 -or $existing.Actions[0].Execute -ne $powershell -or
    $existing.Actions[0].WorkingDirectory -ne $root -or $existing.Actions[0].Arguments -ne $arguments -or
    [string]$existing.State -ne 'Disabled')) {
    throw 'An existing weekly task does not match the disabled task prepared for this cutover.'
}
if ($PSCmdlet.ShouldProcess("$dailyName to $weeklyName", 'Switch to weekly Monday 08:00 after production verification')) {
    if ($existing) {
        Set-ScheduledTask -TaskName $weeklyName -TaskPath '\' -Action $action -Trigger $trigger `
            -Settings $settings -Principal $principal | Out-Null
    } else {
        Register-ScheduledTask -TaskName $weeklyName -TaskPath '\' -InputObject $definition | Out-Null
    }
    $dailyWasEnabled = [string]$daily.State -ne 'Disabled'
    try {
        if ($dailyWasEnabled) { Disable-ScheduledTask -TaskName $dailyName -TaskPath '\' | Out-Null }
        Enable-ScheduledTask -TaskName $weeklyName -TaskPath '\' | Out-Null
        $weekly = Get-ScheduledTask -TaskName $weeklyName -TaskPath '\'
        $next = (Get-ScheduledTaskInfo -TaskName $weeklyName -TaskPath '\').NextRunTime
        if ([string](Get-ScheduledTask -TaskName $dailyName -TaskPath '\').State -ne 'Disabled' -or
            [string]$weekly.State -ne 'Ready' -or $next -ne $nextMonday) {
            throw 'The enabled tasks or next run time did not match the cutover plan.'
        }
    } catch {
        Disable-ScheduledTask -TaskName $weeklyName -TaskPath '\' | Out-Null
        if ($dailyWasEnabled) { Enable-ScheduledTask -TaskName $dailyName -TaskPath '\' | Out-Null }
        throw
    }
    [pscustomobject]@{
        Daily = 'Disabled'
        Weekly = [string]$weekly.State
        NextRunTime = $next
        TimeZone = (Get-TimeZone).Id
        VerifiedMain = $localSha
    }
}
