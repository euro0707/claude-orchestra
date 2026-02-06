# Claude Code Session Sync Script for TetsuyaSynapse
# Reference: https://zenn.dev/pepabo/articles/ffb79b5279f6ee

param(
    [int]$CheckInterval = 5
)

$ClaudeProjectsDir = [System.IO.Path]::Combine($env:USERPROFILE, ".claude", "projects")
$VaultSessionsDir = [System.IO.Path]::Combine($env:USERPROFILE, ".claude", "obsidian-sessions")
$StateFile = [System.IO.Path]::Combine($env:USERPROFILE, ".claude", "sync-state.json")

function Get-SyncState {
    if (Test-Path $StateFile) {
        try {
            return Get-Content $StateFile -Raw | ConvertFrom-Json
        }
        catch {
            return @{ lastSyncedLines = @{} }
        }
    }
    return @{ lastSyncedLines = @{} }
}

function Save-SyncState {
    param($state)
    $state | ConvertTo-Json -Depth 10 | Set-Content $StateFile -Encoding UTF8
}

function Get-ActiveSessionFile {
    $cutoffTime = (Get-Date).AddMinutes(-60)
    Get-ChildItem -Path $ClaudeProjectsDir -Recurse -Filter "*.jsonl" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $cutoffTime -and $_.Length -gt 1000 -and $_.Name -notmatch "^agent-" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Extract-Conversations {
    param($jsonlPath, $startLine)

    $lines = Get-Content $jsonlPath -Encoding UTF8
    $conversations = @()

    for ($i = $startLine; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        try {
            $entry = $line | ConvertFrom-Json
            $content = $null
            $role = $null
            $timestamp = Get-Date

            if (($entry.type -eq "human" -or $entry.type -eq "user") -and $entry.message) {
                $role = "user"
                if ($entry.message.content -is [string]) {
                    $content = $entry.message.content
                }
                elseif ($entry.message.content -is [array]) {
                    $textParts = $entry.message.content | Where-Object { $_.type -eq "text" } | ForEach-Object { $_.text }
                    $content = $textParts -join "`n"
                }
            }
            elseif ($entry.type -eq "assistant" -and $entry.message) {
                $role = "assistant"
                if ($entry.message.content -is [string]) {
                    $content = $entry.message.content
                }
                elseif ($entry.message.content -is [array]) {
                    $textParts = $entry.message.content | Where-Object { $_.type -eq "text" } | ForEach-Object { $_.text }
                    $content = $textParts -join "`n"
                }
            }

            if ($entry.timestamp) {
                try { $timestamp = [DateTime]::Parse($entry.timestamp) } catch {}
            }

            if ($content -and $content.Length -gt 10) {
                if ($content -notmatch "<local-command|<command-name>|<system-reminder>|<task-notification>") {
                    if ($content -notmatch "^No response requested") {
                        $conversations += @{
                            role = $role
                            content = $content
                            timestamp = $timestamp
                        }
                    }
                }
            }
        }
        catch {
            continue
        }
    }

    return $conversations
}

function Convert-ToMarkdown {
    param($conversations, $date, $isNew)

    $md = ""
    if ($isNew) {
        $md = "---`ndate: $($date.ToString('yyyy-MM-dd'))`ntags: [claude-session, auto-sync]`n---`n`n# Claude Session - $($date.ToString('yyyy-MM-dd'))`n"
    }

    foreach ($conv in $conversations) {
        $time = $conv.timestamp.ToString('HH:mm')
        $role = if ($conv.role -eq "user") { "**User**" } else { "**Claude**" }
        $content = if ($conv.content.Length -gt 2000) { $conv.content.Substring(0, 2000) + "`n...(truncated)..." } else { $conv.content }
        $md += "`n## [$time] $role`n`n$content`n`n---`n"
    }

    return $md
}

function Sync-Sessions {
    $state = Get-SyncState
    $sessionFile = Get-ActiveSessionFile

    if (-not $sessionFile) { return }

    $filePath = $sessionFile.FullName
    $fileKey = $filePath -replace "[\\:]", "_"
    $lastLine = if ($state.lastSyncedLines.$fileKey) { $state.lastSyncedLines.$fileKey } else { 0 }
    $currentLineCount = (Get-Content $filePath -Encoding UTF8).Count

    if ($currentLineCount -le $lastLine) { return }

    Write-Host "$(Get-Date -Format 'HH:mm:ss') - Syncing: $($sessionFile.Name)"

    $conversations = Extract-Conversations -jsonlPath $filePath -startLine $lastLine

    if ($conversations.Count -gt 0) {
        Write-Host "  Found $($conversations.Count) messages"
        $grouped = $conversations | Group-Object { $_.timestamp.ToString('yyyy-MM-dd') }

        foreach ($group in $grouped) {
            $date = [DateTime]::Parse($group.Name)
            $dailyFile = Join-Path $VaultSessionsDir "$($date.ToString('yyyy-MM-dd'))_auto.md"
            $isNew = -not (Test-Path $dailyFile)
            $content = Convert-ToMarkdown -conversations $group.Group -date $date -isNew $isNew

            if ($isNew) {
                Set-Content -Path $dailyFile -Value $content -Encoding UTF8
            }
            else {
                Add-Content -Path $dailyFile -Value $content -Encoding UTF8
            }
            Write-Host "  -> $($date.ToString('yyyy-MM-dd'))_auto.md"
        }
    }

    # Update state
    $newState = @{
        lastSyncedLines = @{}
    }
    if ($state.lastSyncedLines) {
        foreach ($key in $state.lastSyncedLines.PSObject.Properties.Name) {
            $newState.lastSyncedLines[$key] = $state.lastSyncedLines.$key
        }
    }
    $newState.lastSyncedLines[$fileKey] = $currentLineCount
    Save-SyncState -state $newState
}

# Main
Write-Host "========================================"
Write-Host "Claude Session Sync for TetsuyaSynapse"
Write-Host "========================================"
Write-Host "Watching: $ClaudeProjectsDir"
Write-Host "Output:   $VaultSessionsDir"
Write-Host "Interval: ${CheckInterval}s"
Write-Host "Press Ctrl+C to stop"
Write-Host "----------------------------------------"

if (-not (Test-Path $VaultSessionsDir)) {
    New-Item -ItemType Directory -Path $VaultSessionsDir -Force | Out-Null
}

while ($true) {
    try { Sync-Sessions }
    catch { Write-Host "Error: $_" -ForegroundColor Red }
    Start-Sleep -Seconds $CheckInterval
}
