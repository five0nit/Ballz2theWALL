#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Ballz2theWALL'),
    [switch]$NonInteractive,
    [switch]$NoLaunch,
    [switch]$NoShortcut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:Window = $null
$script:StatusLabel = $null
$script:LogPath = $null
$lock = $null
$downloadClient = $null
$exitCode = 0
# Save and restore process-local settings even when invoked from an existing shell.
$environmentNames = @('UV_PYTHON_INSTALL_DIR', 'UV_CACHE_DIR', 'UV_PYTHON_DOWNLOADS', 'UV_PYTHON_PREFERENCE')
$savedEnvironment = @{}
foreach ($name in $environmentNames) { $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$originalTls = [Net.ServicePointManager]::SecurityProtocol

function Update-Status([string]$Message) {
    Write-Host $Message
    if ($script:LogPath) { Add-Content -LiteralPath $script:LogPath -Value $Message -Encoding UTF8 }
    if ($script:StatusLabel) {
        $script:StatusLabel.Text = $Message
        [Windows.Forms.Application]::DoEvents()
    }
}

function Quote-Argument([string]$Value) {
    # Windows CommandLineToArgvW quoting: preserve spaces, metacharacters and trailing slashes.
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}

function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = (($Arguments | ForEach-Object { Quote-Argument $_ }) -join ' ')
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.WorkingDirectory = $InstallRoot
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        if (-not $process.Start()) { throw "Could not start $Executable" }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $timer = [Diagnostics.Stopwatch]::StartNew()
        while (-not $process.WaitForExit(100)) {
            if ($script:Window) { [Windows.Forms.Application]::DoEvents() }
            if ($timer.Elapsed.TotalMinutes -gt 8) {
                $process.Kill()
                throw 'An installation step exceeded eight minutes. Check your connection and retry.'
            }
        }
        $output = $stdout.GetAwaiter().GetResult()
        $errors = $stderr.GetAwaiter().GetResult()
        if ($output) { Add-Content -LiteralPath $script:LogPath -Value $output -Encoding UTF8 }
        if ($errors) { Add-Content -LiteralPath $script:LogPath -Value $errors -Encoding UTF8 }
        if ($process.ExitCode -ne 0) { throw "Installation command failed (exit $($process.ExitCode)).`n$errors" }
        return $output.Trim()
    } finally { $process.Dispose() }
}

try {
    if (-not $NonInteractive) {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        [Windows.Forms.Application]::EnableVisualStyles()
        $intro = @"
Install Ballz2theWALL for this Windows account?

Setup downloads a private Python runtime and installs the app. No existing Python, administrator access, or PATH changes are required.

The next wizard connects your agent and presents one ON/OFF control. Installing alone does not change agent profiles or grant blanket access. Ordinary terminal access uses your current Windows account; administrator-only tasks may separately require your approval of a Windows UAC prompt.

Install location: $InstallRoot
"@
        $answer = [Windows.Forms.MessageBox]::Show($intro, 'Ballz2theWALL Setup', 'OKCancel', 'Information')
        if ($answer -ne [Windows.Forms.DialogResult]::OK) { exit 0 }
        $script:Window = New-Object Windows.Forms.Form
        $script:Window.Text = 'Installing Ballz2theWALL'
        $script:Window.ClientSize = New-Object Drawing.Size(570, 135)
        $script:Window.StartPosition = 'CenterScreen'
        $script:Window.FormBorderStyle = 'FixedDialog'
        $script:Window.ControlBox = $false
        $script:StatusLabel = New-Object Windows.Forms.Label
        $script:StatusLabel.Location = New-Object Drawing.Point(20, 20)
        $script:StatusLabel.Size = New-Object Drawing.Size(530, 60)
        $script:Window.Controls.Add($script:StatusLabel)
        $bar = New-Object Windows.Forms.ProgressBar
        $bar.Location = New-Object Drawing.Point(20, 92)
        $bar.Size = New-Object Drawing.Size(530, 20)
        $bar.Style = 'Marquee'
        $script:Window.Controls.Add($bar)
        $script:Window.Show()
    }

    $InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
    if ($InstallRoot -eq [IO.Path]::GetPathRoot($InstallRoot)) { throw 'Choose a dedicated product directory, not a drive root.' }
    $runtime = Join-Path $InstallRoot 'runtime'
    New-Item -ItemType Directory -Force -Path $runtime | Out-Null
    $lock = [IO.File]::Open((Join-Path $runtime 'installer.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $script:LogPath = Join-Path $runtime ('install-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff') + '.log')
    Update-Status 'Checking installation package...'
    # This path works in source installers/ and in an extracted release bundle.
    $bundleRoot = Split-Path -Parent $PSScriptRoot
    $payload = Join-Path $bundleRoot 'payload'
    $wheels = @(Get-ChildItem -LiteralPath $payload -Filter '*.whl' -File -ErrorAction SilentlyContinue)
    $packageHash = $null
    if ($wheels.Count -gt 0) {
        if ($wheels.Count -ne 1) { throw 'The payload must contain exactly one application wheel.' }
        $manifestPath = Join-Path $payload 'SHA256SUMS.json'
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'The wheel checksum manifest is missing. Download a complete release bundle.' }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        $entry = @($manifest.PSObject.Properties | Where-Object { $_.Name -ceq $wheels[0].Name })
        if ($entry.Count -ne 1 -or $entry[0].Value -isnot [string] -or $entry[0].Value -cnotmatch '^[a-fA-F0-9]{64}$') {
            throw 'The wheel checksum manifest has no valid SHA-256 for this wheel.'
        }
        $packageHash = (Get-FileHash -LiteralPath $wheels[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($packageHash -ne $entry[0].Value.ToLowerInvariant()) { throw 'Wheel SHA-256 mismatch. No package was installed; download the bundle again.' }
        $package = $wheels[0].FullName
    } else {
        if (Test-Path -LiteralPath $payload) { throw 'The release payload contains no wheel. Download a complete bundle.' }
        $package = Split-Path -Parent $bundleRoot
        if (-not (Test-Path -LiteralPath (Join-Path $package 'pyproject.toml') -PathType Leaf)) {
            throw 'No release wheel or source pyproject.toml was found. Extract the entire download before running setup.'
        }
    }

    $architecture = $env:PROCESSOR_ARCHITEW6432
    if (-not $architecture) { $architecture = $env:PROCESSOR_ARCHITECTURE }
    $uvVersion = '0.12.5'
    switch ($architecture.ToUpperInvariant()) {
        'AMD64' {
            $asset = 'uv-x86_64-pc-windows-msvc.zip'
            $expectedHash = '4c4d49d8738847d9b71ba319e49a5688c93eac0fe6204b1df24e98528dddf39a'
        }
        'ARM64' {
            $asset = 'uv-aarch64-pc-windows-msvc.zip'
            $expectedHash = '724279317fee6e5fa8ad1908e4eba2bbe764ef1ece5b3f4597927b62b1fe562a'
        }
        default { throw "Unsupported Windows architecture: $architecture. Use 64-bit Windows on x64 or ARM64." }
    }
    $bootstrap = Join-Path $runtime ('bootstrap-' + $uvVersion)
    New-Item -ItemType Directory -Force -Path $bootstrap | Out-Null
    $archive = Join-Path $bootstrap $asset
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
        Update-Status 'Downloading the verified private installer (uv)...'
        [Net.ServicePointManager]::SecurityProtocol = $originalTls -bor [Net.SecurityProtocolType]::Tls12
        $downloadClient = New-Object Net.WebClient
        $partial = $archive + '.partial'
        $task = $downloadClient.DownloadFileTaskAsync([Uri]"https://github.com/astral-sh/uv/releases/download/$uvVersion/$asset", $partial)
        $timer = [Diagnostics.Stopwatch]::StartNew()
        while (-not $task.IsCompleted) {
            Start-Sleep -Milliseconds 100
            if ($script:Window) { [Windows.Forms.Application]::DoEvents() }
            if ($timer.Elapsed.TotalMinutes -gt 3) { $downloadClient.CancelAsync(); throw 'Installer download timed out. Check your connection and retry.' }
        }
        $task.GetAwaiter().GetResult() | Out-Null
        if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
            Remove-Item -LiteralPath $partial -Force
            throw 'uv download SHA-256 mismatch. The untrusted archive was not executed.'
        }
        Move-Item -LiteralPath $partial -Destination $archive -Force
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
        throw "Cached uv archive SHA-256 mismatch. Remove only $archive and retry."
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $bootstrap -Force
    $uvFiles = @(Get-ChildItem -LiteralPath $bootstrap -Filter 'uv.exe' -Recurse -File)
    if ($uvFiles.Count -ne 1) { throw 'The verified uv archive did not contain exactly one uv.exe.' }
    $uv = $uvFiles[0].FullName
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $runtime 'python'
    $env:UV_CACHE_DIR = Join-Path $runtime 'cache'
    $env:UV_PYTHON_DOWNLOADS = 'automatic'
    # uv rejects --managed-python alongside UV_PYTHON_PREFERENCE, even if equivalent.
    $env:UV_PYTHON_PREFERENCE = $null
    $venv = Join-Path $runtime 'venv'
    $python = Join-Path $venv 'Scripts\python.exe'
    Update-Status 'Preparing private Python 3.11 (first installation may take a few minutes)...'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        Invoke-Checked $uv @('venv', '--no-config', '--python', '3.11', '--managed-python', $venv) | Out-Null
    }
    Update-Status 'Installing Ballz2theWALL without changing agent profiles...'
    Invoke-Checked $uv @('pip', 'install', '--no-config', '--python', $python, '--reinstall-package', 'ballz2thewall', $package) | Out-Null
    $version = Invoke-Checked $python @('-I', '-m', 'ballz2thewall', '--version')
    if ($version -notmatch '^Ballz2theWALL ') { throw 'The installed application did not pass its version check.' }
    $shortcutPath = $null
    if (-not $NoShortcut) {
        Update-Status 'Creating your Start Menu setup shortcut...'
        $programs = [Environment]::GetFolderPath('Programs')
        $shortcutPath = Join-Path $programs 'Ballz2theWALL.lnk'
        $shell = New-Object -ComObject WScript.Shell
        try {
            $shortcut = $shell.CreateShortcut($shortcutPath)
            $shortcut.TargetPath = $python
            $shortcut.Arguments = '-I -m ballz2thewall setup --gui'
            $shortcut.WorkingDirectory = $InstallRoot
            $shortcut.Description = 'Connect your agent and switch native access ON or OFF'
            $shortcut.WindowStyle = 1
            $shortcut.Save()
            $check = $shell.CreateShortcut($shortcutPath)
            if ($check.TargetPath -ne $python -or $check.Arguments -ne $shortcut.Arguments) { throw 'Start Menu shortcut verification failed.' }
        } finally { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) | Out-Null }
    }
    $receiptPath = Join-Path $runtime 'install-receipt.json'
    $receipt = [ordered]@{
        status = 'installed'; application = $version; install_root = $InstallRoot; python = $python
        uv_version = $uvVersion; uv_archive_sha256 = $expectedHash; package = $package; package_sha256 = $packageHash
        shortcut = $shortcutPath; profiles_changed = $false; log = $script:LogPath
        installed_at = [DateTime]::UtcNow.ToString('o')
    }
    $receipt | ConvertTo-Json | Set-Content -LiteralPath $receiptPath -Encoding UTF8
    $verifiedReceipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    if ($verifiedReceipt.python -ne $python -or $verifiedReceipt.status -ne 'installed') { throw 'Installation receipt verification failed.' }
    Update-Status "Installed $version. Receipt: $receiptPath"
    if ($script:Window) { $script:Window.Close(); $script:Window.Dispose(); $script:Window = $null; $script:StatusLabel = $null }
    if (-not $NoLaunch) {
        # The parent-owned wizard handles profile selection and explicit ON/OFF consent.
        Start-Process -FilePath $python -ArgumentList '-I -m ballz2thewall setup --gui' -WorkingDirectory $InstallRoot | Out-Null
    } elseif (-not $NonInteractive) {
        [Windows.Forms.MessageBox]::Show('Installation complete. Open Ballz2theWALL from the Start Menu when you are ready to connect your agent.', 'Ballz2theWALL Setup', 'OK', 'Information') | Out-Null
    }
} catch {
    $exitCode = 1
    $message = $_.Exception.Message
    if ($script:LogPath) {
        Add-Content -LiteralPath $script:LogPath -Value ("ERROR: " + $message) -Encoding UTF8 -ErrorAction SilentlyContinue
        $message += "`n`nInstallation log: $script:LogPath"
    }
    if ($script:Window) { $script:Window.Close() }
    if (-not $NonInteractive) {
        try { [Windows.Forms.MessageBox]::Show($message, 'Ballz2theWALL installation failed', 'OK', 'Error') | Out-Null } catch { Write-Warning $message }
    }
    [Console]::Error.WriteLine($message)
} finally {
    if ($downloadClient) { $downloadClient.Dispose() }
    if ($lock) { $lock.Dispose() }
    if ($script:Window) { $script:Window.Dispose() }
    foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process') }
    [Net.ServicePointManager]::SecurityProtocol = $originalTls
}
exit $exitCode
