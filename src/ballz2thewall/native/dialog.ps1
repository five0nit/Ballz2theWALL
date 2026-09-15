[CmdletBinding()]
param([string]$RenderOnly)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$form = New-Object System.Windows.Forms.Form
$form.Text = [string]$data.title
$form.ClientSize = New-Object System.Drawing.Size(600, 410)
$form.StartPosition = 'CenterScreen'
$form.AutoScaleMode = 'Dpi'
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$label = New-Object System.Windows.Forms.Label
$label.Text = [string]$data.message
$label.Location = New-Object System.Drawing.Point(24, 22)
$label.Size = New-Object System.Drawing.Size(552, 210)
$label.AutoEllipsis = $false
$form.Controls.Add($label)
$options = @($data.options)
$short = $options.Count -le 3
foreach ($option in $options) {
    if ([string]$option -match '[\r\n]' -or ([string]$option).Length -gt 28) { $short = $false }
}
$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Cancel'
$cancel.Location = New-Object System.Drawing.Point(458, 350)
$cancel.Size = New-Object System.Drawing.Size(118, 36)
$cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.CancelButton = $cancel
if ($short) {
    $form.ClientSize = New-Object System.Drawing.Size(600, 302)
    for ($i = 0; $i -lt $options.Count; $i++) {
        $button = New-Object System.Windows.Forms.Button
        $button.Text = [string]$options[$i]
        $button.Tag = [string]$options[$i]
        $button.Location = New-Object System.Drawing.Point((24 + $i * 186), 244)
        $button.Size = New-Object System.Drawing.Size(180, 36)
        $button.Add_Click({
            param($sender, $eventArgs)
            $window = $sender.FindForm()
            $window.Tag = $sender.Tag
            $window.DialogResult = [System.Windows.Forms.DialogResult]::OK
            $window.Close()
        })
        $form.Controls.Add($button)
        if ($i -eq 0) { $form.AcceptButton = $button }
    }
} else {
    $list = New-Object System.Windows.Forms.ListBox
    $list.Location = New-Object System.Drawing.Point(24, 232)
    $list.Size = New-Object System.Drawing.Size(552, 100)
    foreach ($option in $options) { [void]$list.Items.Add(([string]$option -replace '[\r\n]+', ' - ')) }
    $list.SelectedIndex = 0
    $list.HorizontalScrollbar = $true
    $form.Controls.Add($list)
    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = 'Continue'
    $ok.Location = New-Object System.Drawing.Point(330, 350)
    $ok.Size = New-Object System.Drawing.Size(118, 36)
    $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Controls.Add($ok)
    $form.Controls.Add($cancel)
    $form.AcceptButton = $ok
}
if ($RenderOnly) {
    # Developer QA only: render this exact form without showing it or taking focus.
    $form.CreateControl()
    $bitmap = New-Object System.Drawing.Bitmap($form.Width, $form.Height)
    $form.DrawToBitmap($bitmap, (New-Object System.Drawing.Rectangle(0, 0, $form.Width, $form.Height)))
    # Invisible parent forms skip their child paint pass. Render each real child
    # at its native layout coordinates; never show/activate a QA window.
    $edge = [int](($form.Width - $form.ClientSize.Width) / 2)
    $caption = $form.Height - $form.ClientSize.Height - $edge
    foreach ($control in $form.Controls) {
        $control.CreateControl()
        $rectangle = New-Object System.Drawing.Rectangle(($edge + $control.Left), ($caption + $control.Top), $control.Width, $control.Height)
        $control.DrawToBitmap($bitmap, $rectangle)
    }
    $bitmap.Save($RenderOnly, [System.Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
    @{ rendered = $RenderOnly; native_buttons = @($form.Controls | Where-Object { $_ -is [System.Windows.Forms.Button] } | ForEach-Object { $_.Text }) } | ConvertTo-Json -Compress
} else {
    $result = $form.ShowDialog()
    $choice = $null
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        if ($short) { $choice = [string]$form.Tag }
        else { $choice = [string]$options[$list.SelectedIndex] }
    }
    @{ choice = $choice } | ConvertTo-Json -Compress
}
$form.Dispose()
$cancel.Dispose()
