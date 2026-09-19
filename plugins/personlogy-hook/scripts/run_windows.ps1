param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('capture.py', 'sender.py')]
    [string]$ScriptName,

    [Parameter(ValueFromRemainingArguments = $true, Position = 1)]
    [string[]]$ScriptArguments
)

$ErrorActionPreference = 'Stop'

$pluginRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $pluginRoot)
$scriptPath = Join-Path $pluginRoot "scripts\$ScriptName"

if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    [Console]::Error.WriteLine("PersonLogy Hook script not found: $scriptPath")
    exit 127
}

$pythonPath = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$pythonArguments = @()

if (Test-Path -LiteralPath $pythonPath -PathType Leaf) {
    $pythonCommand = $pythonPath
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = 'py'
    $pythonArguments = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = 'python'
} else {
    [Console]::Error.WriteLine(
        'PersonLogy Hook requires Python. No .venv\Scripts\python.exe, py -3, or python was found.'
    )
    exit 127
}

& $pythonCommand @pythonArguments $scriptPath @ScriptArguments
exit $LASTEXITCODE
