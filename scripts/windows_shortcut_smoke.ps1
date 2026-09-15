# Native COM shortcut verification, with only Programs redirected to a scratch directory.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Source,
      [Parameter(Mandatory=$true)][string]$InstallRoot,
      [Parameter(Mandatory=$true)][string]$Python,
      [Parameter(Mandatory=$true)][string]$TestPrograms)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($Source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Installer did not parse' }
$NoShortcut = $false
$script:LogPath = $null
$script:StatusLabel = $null
$update = $ast.Find({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Update-Status' }, $true)
. ([ScriptBlock]::Create($update.Extent.Text))
$save = $ast.Find({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Save-SetupShortcut' }, $true)
. ([ScriptBlock]::Create($save.Extent.Text))
$blocks = @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.IfStatementAst] -and $n.Extent.Text.StartsWith('if (-not $NoShortcut)') }, $true))
if ($blocks.Count -ne 1) { throw 'Expected exactly one shortcut block' }
New-Item -ItemType Directory -Path $TestPrograms -Force | Out-Null
# The native creation and readback block stays unchanged; no real Start Menu write.
$block = $blocks[0].Extent.Text.Replace("[Environment]::GetFolderPath('Programs')", '$TestPrograms')
. ([ScriptBlock]::Create($block))
if (-not (Test-Path -LiteralPath $shortcutPath)) { throw 'Shortcut missing' }
$shell = New-Object -ComObject WScript.Shell
try {
    $link = $shell.CreateShortcut($shortcutPath)
    if ($link.TargetPath -ne $Python -or $link.Arguments -ne '-I -m ballz2thewall setup --gui' -or $link.WorkingDirectory -ne $InstallRoot) { throw 'Shortcut readback mismatch' }
    [ordered]@{status='passed'; scope='native COM; scratch Programs override'; shortcut=$shortcutPath; target=$link.TargetPath; arguments=$link.Arguments; working_directory=$link.WorkingDirectory; installer_sha256=(Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()} | ConvertTo-Json
} finally { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) | Out-Null }
