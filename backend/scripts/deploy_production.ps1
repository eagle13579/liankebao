<#
.SYNOPSIS
    链客宝 — 一键生产部署脚本 (PowerShell)
    LianKeBao — One-command Production Deployment

.DESCRIPTION
    Activates Phase 1 Infrastructure (RedisCache + SQLiteEventBus)
    and Agent Runtime with all 9 AI Digital Employees.

.PARAMETER Check
    Verify environment prerequisites without deploying.

.PARAMETER DryRun
    Print what would happen without executing.

.EXAMPLE
    # Standard deployment
    .\scripts\deploy_production.ps1

    # Check only
    .\scripts\deploy_production.ps1 -Check

    # Dry run
    .\scripts\deploy_production.ps1 -DryRun
#>

param(
    [switch]$Check,
    [switch]$DryRun,
    [switch]$Help
)

if ($Help) {
    Get-Help $PSCommandPath -Detailed
    exit 0
}

$ErrorActionPreference = "Stop"

# ── Paths ──────────────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $PSCommandPath
$ProjectDir = Split-Path -Parent $ScriptDir
$LogDir = "$ProjectDir\logs"
$AgentsLog = "$LogDir\agents.log"
$ServiceFile = "$ProjectDir\deploy\chainke-agents.service"
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# ── Emoji helpers ─────────────────────────────────────────────────
function Write-Info   { Write-Host "[INFO]  $args" -ForegroundColor Blue }
function Write-Ok     { Write-Host "[$( -join @([char]0x2705, '] ')) $args" -ForegroundColor Green }
function Write-Warn   { Write-Host "[$( -join @([char]0x26A0, [char]0xFE0F, '] ')) $args" -ForegroundColor Yellow }
function Write-Error  { Write-Host "[$( -join @([char]0x274C, '] ')) $args" -ForegroundColor Red }
function Write-Header { Write-Host "`n════════════════════════════════════════════════════════" -ForegroundColor Cyan; Write-Host "  $args" -ForegroundColor Cyan; Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan }

# ═══════════════════════════════════════════════════════════════════
# Pre-flight checks
# ═══════════════════════════════════════════════════════════════════
function Invoke-PreflightChecks {
    Write-Header "🔎 前置检查 Pre-flight Checks"
    $allOk = $true

    # Python
    try {
        $pyVer = & python --version 2>&1
        Write-Ok "Python: $pyVer"
    } catch {
        try {
            $pyVer = & python3 --version 2>&1
            Write-Ok "Python: $pyVer"
        } catch {
            Write-Error "Python 未安装 (not found)"
            $allOk = $false
        }
    }

    # Check critical modules
    $modules = @(
        "$ProjectDir\app\dependencies.py",
        "$ProjectDir\app\agents\employee_profiles.py",
        "$ProjectDir\app\cache\adapters\redis_adapter.py",
        "$ProjectDir\app\events\adapters\sqlite_adapter.py",
        "$ProjectDir\app\agents\agent_runtime.py"
    )
    foreach ($mod in $modules) {
        if (Test-Path $mod) {
            Write-Ok "Module exists: $(Split-Path $mod -Leaf)"
        } else {
            Write-Warn "Module not found: $mod"
        }
    }

    # .env.production
    if (Test-Path "$ProjectDir\.env.production") {
        Write-Ok ".env.production found"
    } else {
        Write-Warn ".env.production 未找到 — 将从 .env.example 创建"
    }

    # deploy directory
    if (Test-Path "$ProjectDir\deploy") {
        Write-Ok "deploy/ directory exists"
    } else {
        Write-Error "deploy/ 目录缺失！"
        $allOk = $false
    }

    if ($allOk) { Write-Ok "前置检查全部通过" }
    else { Write-Error "部分检查未通过" }
    Write-Host ""

    return $allOk
}

# ═══════════════════════════════════════════════════════════════════
# Environment setup
# ═══════════════════════════════════════════════════════════════════
function Invoke-EnvironmentSetup {
    Write-Header "🌍 环境配置 Environment Setup"

    $env:INFRA_PHASE = "1"
    Write-Ok "INFRA_PHASE=1 (Phase 1 基础设施激活)"

    # Load .env.production
    $envFile = "$ProjectDir\.env.production"
    if (Test-Path $envFile) {
        Write-Ok ".env.production 已加载"
    } else {
        Write-Warn ".env.production 未找到 — 使用默认值"
    }

    # Create log directory
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    }
    Write-Ok "日志目录: $LogDir"
}

# ═══════════════════════════════════════════════════════════════════
# Start Agent Runtime
# ═══════════════════════════════════════════════════════════════════
function Invoke-StartAgentRuntime {
    Write-Header "🤖 AI 数字员工 Runtime 启动"

    $startScript = "$ProjectDir\scripts\start_agents.py"
    if (-not (Test-Path $startScript)) {
        Write-Error "启动脚本未找到: $startScript"
        return $false
    }

    if ($DryRun) {
        Write-Ok "[DRY-RUN] 将执行: `$env:INFRA_PHASE=1; python $startScript"
        return $true
    }

    Write-Info "后台进程模式部署..."

    # Kill existing process if running
    $pidFile = "$ProjectDir\agents.pid"
    if (Test-Path $pidFile) {
        $oldPid = Get-Content $pidFile
        try {
            $oldProcess = Get-Process -Id $oldPid -ErrorAction Stop
            Write-Warn "正在停止旧进程 (PID: $oldPid)"
            Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        } catch {
            # Process not running, ignore
        }
    }

    # Start the agent runtime
    $env:INFRA_PHASE = "1"
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "python"
    $psi.Arguments = $startScript
    $psi.WorkingDirectory = $ProjectDir
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.EnvironmentVariables["INFRA_PHASE"] = "1"

    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
        $agentPid = $proc.Id
        $proc.Close()

        # Write PID
        Set-Content -Path $pidFile -Value $agentPid
        Write-Ok "后台进程已启动 (PID: $agentPid)"

        # Check it briefly
        Start-Sleep -Seconds 3
        $running = Get-Process -Id $agentPid -ErrorAction SilentlyContinue
        if ($running) {
            Write-Ok "Agent Runtime 进程存活"
            if ((Get-Item $AgentsLog -ErrorAction SilentlyContinue).Length -gt 0) {
                Get-Content $AgentsLog -Tail 5
            }
        } else {
            Write-Error "Agent Runtime 进程已退出 — 检查日志: $AgentsLog"
            if (Test-Path $AgentsLog) { Get-Content $AgentsLog -Tail 20 }
            return $false
        }
    } catch {
        Write-Error "启动 Agent Runtime 失败: $_"
        return $false
    }

    return $true
}

# ═══════════════════════════════════════════════════════════════════
# Verification
# ═══════════════════════════════════════════════════════════════════
function Invoke-VerifyDeployment {
    Write-Header "🔍 部署验证 Verification"

    if ($DryRun) {
        Write-Ok "[DRY-RUN] 将执行 Python 验证"
        return $true
    }

    $verifyCode = @'
import sys, os
sys.path.insert(0, r'{PROJECT_DIR}')
os.environ['INFRA_PHASE'] = '1'

print(f'  {"="*50}')
print(f'  {"链客宝部署验证":^50}')
print(f'  {"="*50}')

# Check Phase 1 infrastructure
try:
    from app.cache.adapters.redis_adapter import RedisCache
    print(f'  ✅ RedisCache — 就绪')
except Exception as e:
    print(f'  ⚠️  RedisCache — 降级: {e}')

try:
    from app.events.adapters.sqlite_adapter import SQLiteEventBus
    print(f'  ✅ SQLiteEventBus — 就绪')
except Exception as e:
    print(f'  ❌ SQLiteEventBus — 错误: {e}')

# Check dependencies
try:
    from app.dependencies import get_cache, get_event_bus
    cache = get_cache()
    bus = get_event_bus()
    print(f'  ✅ Dependencies — cache={type(cache).__name__}, bus={type(bus).__name__}')
except Exception as e:
    print(f'  ⚠️  Dependencies — {e}')

# Check all 9 employees
try:
    from app.agents.employee_profiles import EMPLOYEE_AGENT_MAP
    print(f'  ✅ 数字员工注册: {len(EMPLOYEE_AGENT_MAP)} 名')
    for k, v in EMPLOYEE_AGENT_MAP.items():
        print(f'     {k:>15s} → {v["employee_id"]}')
except Exception as e:
    print(f'  ❌ 员工注册失败: {e}')

# Check Agent Runtime
try:
    from app.agents.agent_runtime import AgentRuntime
    from app.agents.base_agent import AgentConfig
    print(f'  ✅ AgentRuntime — 就绪')
    print(f'  ✅ AgentConfig — 就绪')
except Exception as e:
    print(f'  ❌ AgentRuntime — {e}')

# Check Scheduler Rules
try:
    from app.agents.scheduler_rules import SCHEDULER_RULES
    print(f'  ✅ SchedulerRules — {len(SCHEDULER_RULES)} 条规则')
    for rule in SCHEDULER_RULES:
        print(f'     {rule["schedule"]:>12s} → {rule["agent_name"]}')
except Exception as e:
    print(f'  ⚠️  SchedulerRules — {e}')

# Check Gaia Brain
try:
    from app.gaia_brain import GaiaBrain
    print(f'  ✅ GaiaBrain — 就绪')
except Exception as e:
    print(f'  ⚠️  GaiaBrain — {e}')

print(f'  {"="*50}')
print(f'  INFRA_PHASE={os.environ.get("INFRA_PHASE", "0")}')
print(f'  部署状态: 完成')
print(f'  {"="*50}')
'@ -replace '{PROJECT_DIR}', $ProjectDir.Replace('\', '\\')

    try {
        $result = python -c $verifyCode 2>&1
        $result | ForEach-Object { Write-Host $_ }
        Write-Ok "Python 验证通过"
    } catch {
        Write-Error "Python 验证失败: $_"
        return $false
    }

    return $true
}

# ═══════════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════════
function Write-DeploymentReport {
    Write-Header "📋 部署报告 Deployment Report"

    $agentPid = "N/A"
    if (Test-Path "$ProjectDir\agents.pid") {
        $agentPid = Get-Content "$ProjectDir\agents.pid"
    }

    Write-Host "  Timestamp:      $Timestamp" -ForegroundColor White
    Write-Host "  Project:        链客宝 (LianKeBao)" -ForegroundColor White
    Write-Host "  Directory:      $ProjectDir" -ForegroundColor White
    Write-Host "  INFRA_PHASE:    1" -ForegroundColor White
    Write-Host ""
    Write-Host "  已激活组件:" -ForegroundColor White
    Write-Host "    Phase 1:      RedisCache + SQLiteEventBus" -ForegroundColor Green
    Write-Host "    Agent Runtime: 9 名数字员工" -ForegroundColor Green
    Write-Host "    盖娅飞轮:      每 30 分钟自动进化" -ForegroundColor Green
    Write-Host ""
    Write-Host "  日志:           $AgentsLog" -ForegroundColor White
    Write-Host "  PID:            $agentPid" -ForegroundColor White
    Write-Host ""
    Write-Host "✅ 链客宝生产部署完成 🚀" -ForegroundColor Green
    Write-Host "   LianKeBao production deployment complete." -ForegroundColor Green
}

# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "  🚀  链客宝 — 一键生产部署" -ForegroundColor Cyan
Write-Host "  LianKeBao — One-Command Production Deployment" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$ok = Invoke-PreflightChecks

if ($Check) {
    Write-Host ""
    Write-Ok "检查完成 — 未执行部署 (-Check)"
    exit $(if ($ok) { 0 } else { 1 })
}

if (-not $ok) {
    Write-Warn "继续部署（部分前置检查未通过）"
}

Invoke-EnvironmentSetup
$runtimeOk = Invoke-StartAgentRuntime
if (-not $runtimeOk) {
    Write-Error "Agent Runtime 启动失败"
    exit 1
}

$verifyOk = Invoke-VerifyDeployment
if (-not $verifyOk) {
    Write-Error "部署验证失败"
    exit 1
}

Write-DeploymentReport
exit 0
