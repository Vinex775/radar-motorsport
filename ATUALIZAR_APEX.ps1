# APEX updater: downloads the current public GitHub main branch,
# compares file contents, and copies only new/changed files.
# Existing files are backed up before being replaced.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)

$Owner = 'Vinex775'
$Repository = 'radar-motorsport'
$Branch = 'main'
$ArchiveUrl = "https://codeload.github.com/$Owner/$Repository/zip/refs/heads/$Branch"
$ProjectRoot = $PSScriptRoot
$TempRoot = Join-Path $env:TEMP ("APEX_UPDATE_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + "_" + [guid]::NewGuid().ToString('N').Substring(0, 6))
$BackupRoot = $null
$ExitCode = 0

function Test-ExcludedPath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $normalized = $RelativePath.Replace('/', '\')
    $parts = $normalized -split '\\'
    $excludedDirectories = @(
        '.git', '.venv', 'venv', 'env', '__pycache__',
        '.pytest_cache', '.mypy_cache', '.ruff_cache',
        'node_modules', 'logs', 'cache', '.cache', 'instance'
    )

    foreach ($part in $parts) {
        if ($excludedDirectories -contains $part) {
            return $true
        }
    }

    $leaf = [System.IO.Path]::GetFileName($normalized)

    # Preserve secrets and local runtime data. This intentionally excludes
    # every .env variant, not only the exact .env filename.
    if ($leaf -match '(?i)^\.env($|\.)') { return $true }
    if ($leaf -match '(?i)\.(db|sqlite|sqlite3)(-wal|-shm)?$') { return $true }
    if ($leaf -match '(?i)\.(log|pyc)$') { return $true }
    if ($leaf -in @('ATUALIZAR_APEX.bat', 'ATUALIZAR_APEX.ps1')) { return $true }
    if ($leaf -in @('Thumbs.db', '.DS_Store')) { return $true }

    return $false
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

try {
    Write-Host ''
    Write-Host 'APEX - Atualizador do GitHub' -ForegroundColor Cyan
    Write-Host '-----------------------------------------------'
    Write-Host ("Pasta do projeto: {0}" -f $ProjectRoot)
    Write-Host ("Repositorio: https://github.com/{0}/{1} (branch {2})" -f $Owner, $Repository, $Branch)
    Write-Host ''

    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'app.py')) -or
        -not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'radar.py')) -or
        -not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'collectors') -PathType Container)) {
        throw 'Esta nao parece ser a pasta principal do APEX. Coloque os dois arquivos do atualizador ao lado de app.py, radar.py e da pasta collectors.'
    }

    if (-not $env:TEMP) {
        throw 'A variavel TEMP do Windows nao esta configurada.'
    }

    New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null
    $ArchivePath = Join-Path $TempRoot 'apex-main.zip'
    $ExtractPath = Join-Path $TempRoot 'extraido'
    New-Item -ItemType Directory -Path $ExtractPath -Force | Out-Null

    Write-Host '1/4 - Baixando a versao atual do GitHub...' -ForegroundColor Yellow
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $ArchivePath -UseBasicParsing -Headers @{ 'User-Agent' = 'APEX-Updater-Windows' }

    if (-not (Test-Path -LiteralPath $ArchivePath) -or (Get-Item -LiteralPath $ArchivePath).Length -lt 1000) {
        throw 'O GitHub nao retornou um arquivo de codigo valido.'
    }

    Write-Host '2/4 - Extraindo e comparando os arquivos...' -ForegroundColor Yellow
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ExtractPath -Force

    $RepoRoot = Get-ChildItem -LiteralPath $ExtractPath -Directory |
        Where-Object {
            (Test-Path -LiteralPath (Join-Path $_.FullName 'app.py')) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName 'radar.py'))
        } |
        Select-Object -First 1

    if (-not $RepoRoot) {
        throw 'Nao consegui identificar a estrutura do APEX no arquivo baixado do GitHub.'
    }

    $Changes = New-Object 'System.Collections.Generic.List[object]'
    $SourceFiles = Get-ChildItem -LiteralPath $RepoRoot.FullName -File -Recurse

    foreach ($SourceFile in $SourceFiles) {
        $RelativePath = $SourceFile.FullName.Substring($RepoRoot.FullName.Length).TrimStart('\', '/')
        if (Test-ExcludedPath -RelativePath $RelativePath) { continue }

        $DestinationPath = Join-Path $ProjectRoot $RelativePath
        if (-not (Test-Path -LiteralPath $DestinationPath -PathType Leaf)) {
            $Changes.Add([pscustomobject]@{
                Path = $RelativePath
                Source = $SourceFile.FullName
                Destination = $DestinationPath
                Action = 'NOVO'
                IsNew = $true
            })
        }
        else {
            $LocalHash = Get-Sha256 -Path $DestinationPath
            $RemoteHash = Get-Sha256 -Path $SourceFile.FullName
            if ($LocalHash -ne $RemoteHash) {
                $Changes.Add([pscustomobject]@{
                    Path = $RelativePath
                    Source = $SourceFile.FullName
                    Destination = $DestinationPath
                    Action = 'ATUALIZAR'
                    IsNew = $false
                })
            }
        }
    }

    if ($Changes.Count -eq 0) {
        Write-Host 'Seu APEX ja esta igual aos arquivos disponiveis no GitHub.' -ForegroundColor Green
        Write-Host 'Nenhum arquivo precisou ser alterado.'
        return
    }

    $Changes = @($Changes | Sort-Object Path)
    $NewCount = @($Changes | Where-Object { $_.IsNew }).Count
    $UpdateCount = @($Changes | Where-Object { -not $_.IsNew }).Count

    Write-Host ''
    Write-Host '3/4 - Encontrei estas diferencas:' -ForegroundColor Yellow
    Write-Host '-----------------------------------------------'
    foreach ($Change in $Changes) {
        $color = if ($Change.IsNew) { 'Green' } else { 'Yellow' }
        Write-Host ("[{0}] {1}" -f $Change.Action, $Change.Path) -ForegroundColor $color
    }
    Write-Host '-----------------------------------------------'
    Write-Host ("Arquivos novos: {0} | Arquivos diferentes a substituir: {1}" -f $NewCount, $UpdateCount)
    Write-Host ''
    Write-Host 'Seguranca:' -ForegroundColor Cyan
    Write-Host '- Cada arquivo existente que for substituido tera uma copia de seguranca.'
    Write-Host '- Os backups ficarao em uma pasta APEX_BACKUP_... ao lado da pasta do projeto.'
    Write-Host '- .env, bancos SQLite, logs, caches, ambientes virtuais e .git serao preservados.'
    Write-Host '- Arquivos locais que nao existem mais no GitHub nao serao apagados.'
    Write-Host '- Arquivos diferentes localmente serao substituidos pela versao do GitHub depois da sua confirmacao.'
    Write-Host ''

    $Answer = Read-Host 'Deseja aplicar essas atualizacoes? Digite S para confirmar'
    if ($Answer -notmatch '^(?i)s$') {
        Write-Host 'Atualizacao cancelada. Nenhum arquivo do projeto foi alterado.' -ForegroundColor Yellow
        return
    }

    Write-Host ''
    Write-Host '4/4 - Aplicando somente os arquivos diferentes...' -ForegroundColor Yellow

    $OverwriteCount = @($Changes | Where-Object { -not $_.IsNew }).Count
    if ($OverwriteCount -gt 0) {
        $ParentFolder = Split-Path -Parent $ProjectRoot
        $BackupName = 'APEX_BACKUP_' + (Get-Date -Format 'yyyyMMdd_HHmmss')
        $BackupRoot = Join-Path $ParentFolder $BackupName
        $suffix = 1
        while (Test-Path -LiteralPath $BackupRoot) {
            $BackupRoot = Join-Path $ParentFolder ($BackupName + '_' + $suffix)
            $suffix++
        }
        New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    }

    $BackedUp = New-Object 'System.Collections.Generic.List[object]'
    $Created = New-Object 'System.Collections.Generic.List[string]'

    try {
        foreach ($Change in $Changes) {
            $DestinationDirectory = Split-Path -Parent $Change.Destination
            if (-not (Test-Path -LiteralPath $DestinationDirectory -PathType Container)) {
                New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
            }

            if (Test-Path -LiteralPath $Change.Destination -PathType Leaf) {
                $BackupFile = Join-Path $BackupRoot $Change.Path
                $BackupDirectory = Split-Path -Parent $BackupFile
                if (-not (Test-Path -LiteralPath $BackupDirectory -PathType Container)) {
                    New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null
                }
                Copy-Item -LiteralPath $Change.Destination -Destination $BackupFile -Force
                $BackedUp.Add([pscustomobject]@{ Destination = $Change.Destination; Backup = $BackupFile })
            }
            else {
                $Created.Add($Change.Destination)
            }

            Copy-Item -LiteralPath $Change.Source -Destination $Change.Destination -Force
            Write-Host ("OK: {0}" -f $Change.Path) -ForegroundColor Green
        }
    }
    catch {
        Write-Host ''
        Write-Host 'Ocorreu um erro durante a copia. Tentando restaurar os arquivos anteriores...' -ForegroundColor Red
        foreach ($CreatedFile in $Created) {
            if (Test-Path -LiteralPath $CreatedFile -PathType Leaf) {
                Remove-Item -LiteralPath $CreatedFile -Force -ErrorAction SilentlyContinue
            }
        }
        foreach ($SavedFile in $BackedUp) {
            if (Test-Path -LiteralPath $SavedFile.Backup -PathType Leaf) {
                Copy-Item -LiteralPath $SavedFile.Backup -Destination $SavedFile.Destination -Force -ErrorAction SilentlyContinue
            }
        }
        throw
    }

    Write-Host ''
    Write-Host 'APEX atualizado com sucesso!' -ForegroundColor Green
    Write-Host ("Arquivos novos: {0}" -f $NewCount)
    Write-Host ("Arquivos atualizados: {0}" -f $UpdateCount)
    if ($BackupRoot) {
        Write-Host ("Backup dos arquivos substituidos: {0}" -f $BackupRoot) -ForegroundColor Cyan
    }
    Write-Host ''
    Write-Host 'Reinicie o servidor do APEX e atualize o navegador com Ctrl+F5.'
}
catch {
    $ExitCode = 1
    Write-Host ''
    Write-Host 'ERRO AO ATUALIZAR O APEX:' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ''
    Write-Host 'O atualizador nao remove arquivos antigos do projeto. Se a falha aconteceu durante a copia, ele tentou reverter as alteracoes parciais.'
}
finally {
    if (Test-Path -LiteralPath $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($ExitCode -ne 0) {
    exit $ExitCode
}
