# PersonLogy Agent 本地启动脚本（Windows / PowerShell）
#
# 用法（在仓库根目录运行）：
#   .\start.ps1                 # 启动全部服务（API + Worker + Web）
#   .\start.ps1 -Service api    # 只启动 API
#   .\start.ps1 -Service worker # 只启动 Worker
#   .\start.ps1 -Service web    # 只启动 Web 前端
#   .\start.ps1 -Stop           # 停止全部服务
#   .\start.ps1 -Stop -Service api
#   .\start.ps1 -Status         # 查看各服务状态
#   .\start.ps1 -Restart        # 重启全部
#   .\start.ps1 -Foreground     # 前台运行（调试用，Ctrl+C 退出）
#
# 说明：
#   - 每个服务以独立后台进程运行，日志写入 .logs\ 目录（api.log / worker.log / web.log）
#   - 自动加载根目录 .env（若存在）到当前进程环境
#   - 端口约定：API 8000，Web 5173（与 vite.config.ts / compose.yaml 一致）
#   - 首次使用前需已安装依赖（见 README：.venv 已就绪 + web 需 npm install）

param(
    [ValidateSet("api", "worker", "web")]
    [string]$Service = "",
    [switch]$Stop,
    [switch]$Status,
    [switch]$Restart,
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$logsDir = Join-Path $repoRoot ".logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$py = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "未找到 $py。请先创建虚拟环境并安装依赖。"
    exit 1
}

# ---------- 加载 .env（若存在） ----------
$envFile = Join-Path $repoRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object {
        $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*\s*=' -and $_ -notmatch '^\s*#'
    } | ForEach-Object {
        $kv = $_ -split '=', 2
        $name = $kv[0].Trim()
        $value = $kv[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
    Write-Host "[env] 已加载 .env"
} else {
    Write-Host "[env] 未找到 .env，使用默认配置（可复制 .env.example 为 .env）"
}

$services = @("api", "worker", "web")

# ---------- 各服务启动命令 ----------
function Get-StartCommand([string]$svc) {
    switch ($svc) {
        "api"    { return @{ Name = "api";    Cmd = $py; Args = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"); WorkDir = Join-Path $repoRoot "apps\api"; Log = Join-Path $logsDir "api.log" } }
        "worker" { return @{ Name = "worker"; Cmd = $py; Args = @("-m", "personlogy_worker.main"); WorkDir = Join-Path $repoRoot "apps\worker"; Log = Join-Path $logsDir "worker.log" } }
        "web"    { return @{ Name = "web";    Cmd = "npm.cmd"; Args = @("run", "dev"); WorkDir = Join-Path $repoRoot "apps\web"; Log = Join-Path $logsDir "web.log" } }
    }
    throw "未知服务: $svc"
}

# ---------- 状态 ----------
function Show-Status {
    Write-Host "`n===== PersonLogy 服务状态 ====="
    $found = $false
    foreach ($svc in $services) {
        if ($Service -and $svc -ne $Service) { continue }
        $info = Get-StartCommand $svc
        # 用端口探测判断 API / Web 是否在线；Worker 用日志活跃度
        $detail = "未运行"
        if ($svc -eq "api") {
            try {
                $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/health/live" -TimeoutSec 2 -UseBasicParsing
                $detail = if ($r.StatusCode -eq 200) { "在线" } else { "未运行" }
            } catch { $detail = "未运行" }
        } elseif ($svc -eq "web") {
            try {
                Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 2 -UseBasicParsing | Out-Null
                $detail = "在线"
            } catch { $detail = "未运行" }
        } else {
            # worker：stderr（structlog）或 stdout 日志近 3 分钟有更新视为活跃
            $probeLogs = @($info.Log, "$($info.Log).err") | Where-Object { Test-Path $_ }
            if ($probeLogs) {
                $last = ($probeLogs | Get-Item | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
                $detail = if (((Get-Date) - $last).TotalMinutes -lt 3) { "活跃（近 3 分钟）" } else { "未运行" }
            }
        }
        $logAge = "（无日志）"
        if (Test-Path $info.Log) {
            $last = (Get-Item $info.Log).LastWriteTime
            $ageMin = [math]::Round(((Get-Date) - $last).TotalMinutes, 1)
            $logAge = "日志 ${ageMin} 分钟前更新"
        }
        Write-Host ("  {0,-8} {1,-14} {2}" -f $info.Name, $detail, $logAge)
        $found = $true
    }
    if (-not $found) { Write-Host "  （无匹配服务）" }
    Write-Host ""
}

# ---------- 查找服务进程（按端口 / 命令行） ----------
function Get-ServiceProcesses([string]$svc) {
    switch ($svc) {
        "api" {
            $conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
            return $conns | Select-Object -ExpandProperty OwningProcess -Unique |
                ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue }
        }
        "web" {
            $conns = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
            return $conns | Select-Object -ExpandProperty OwningProcess -Unique |
                ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue }
        }
        "worker" {
            return Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -match "personlogy_worker\.main" } |
                ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        }
    }
    return @()
}

# ---------- 启动单个服务 ----------
function Start-One([string]$svc) {
    $info = Get-StartCommand $svc
    $existing = Get-ServiceProcesses $svc
    if ($existing) {
        Write-Host "[$svc] 已在运行（PID $($existing.Id -join ', ')），跳过"
        return
    }
    Write-Host "[$svc] 启动中..."
    if ($Foreground) {
        # 前台运行（调试用）：直接执行并等待，Ctrl+C 退出
        Push-Location $info.WorkDir
        try {
            $fgArgs = $info.Args
            & $info.Cmd @fgArgs
        } finally {
            Pop-Location
        }
        return
    }
    $proc = Start-Process -FilePath $info.Cmd -ArgumentList $info.Args `
        -WorkingDirectory $info.WorkDir -RedirectStandardOutput $info.Log `
        -RedirectStandardError "$($info.Log).err" -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 800
    Write-Host "[$svc] PID $($proc.Id)，日志: $($info.Log)"
}

# ---------- 停止单个服务 ----------
function Stop-One([string]$svc) {
    $procs = Get-ServiceProcesses $svc
    if (-not $procs) {
        Write-Host "[$svc] 未运行"
        return
    }
    foreach ($p in $procs) {
        try {
            Stop-Process -Id $p.Id -Force -ErrorAction Stop
            Write-Host "[$svc] 已停止（PID $($p.Id)）"
        } catch {
            Write-Host "[$svc] 停止失败（PID $($p.Id)）：$($_.Exception.Message)"
        }
    }
}

# ---------- 主逻辑 ----------
if ($Status) {
    Show-Status
    exit 0
}

$targets = if ($Service) { @($Service) } else { $services }

if ($Restart) {
    foreach ($svc in $targets) { Stop-One $svc }
    Start-Sleep -Seconds 1
    foreach ($svc in $targets) { Start-One $svc }
    Show-Status
    exit 0
}

if ($Stop) {
    foreach ($svc in $targets) { Stop-One $svc }
    exit 0
}

foreach ($svc in $targets) { Start-One $svc }
Show-Status

Write-Host "`n===== 访问入口 ====="
Write-Host "  API 文档:  http://127.0.0.1:8000/docs"
Write-Host "  前端界面:  http://localhost:5173"
Write-Host "  停止全部:  .\start.ps1 -Stop"
Write-Host "  查看状态:  .\start.ps1 -Status"
Write-Host ""
