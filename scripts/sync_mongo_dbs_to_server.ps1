<#
    sync_mongo_dbs_to_server.ps1

    Automatizeaza secventa manuala de dump/copiere/restore pentru mai multe
    baze de date Mongo, din containerul local catre serverul de la
    172.16.64.44. Pentru fiecare nume din $Databases ruleaza, in ordine:

      1. mongodump in interiorul containerului local -> arhiva .gz in /tmp
      2. docker cp arhiva -> Desktop local
      3. scp arhiva -> home-ul userului pe server
      4. ssh pe server: sudo cp in /opt/databases + mongorestore din arhiva

    Cerinte:
      - Docker Desktop pornit local, containerul Mongo local rulind.
      - Client OpenSSH (ssh/scp) disponibil in PATH (vine cu Windows 10/11).
      - Acces SSH catre server cu userul de mai jos (cheie sau parola introdusa
        manual la fiecare prompt - scriptul NU stocheaza nicio parola).
      - Userul de pe server are drept de sudo (pentru "cp" in /opt/databases).

    Editeaza $Databases mai jos cu lista reala de baze de date, apoi ruleaza:
        powershell -File scripts\sync_mongo_dbs_to_server.ps1
#>

$ErrorActionPreference = "Stop"

# ---- Editeaza aici -------------------------------------------------------
$Databases = @(
    "accounts_db",
    # "tx_db",
    # "auth_db"
)

$MongoContainer = "maestrobank-mongodb"
$RemoteHost     = "172.16.64.44"
$RemoteUser     = "calin.bantas"
$RemoteHomeDir  = "/home/$RemoteUser"
$RemoteFinalDir = "/opt/databases"
$LocalDumpDir   = Join-Path $HOME "Desktop"
# ---------------------------------------------------------------------------

if ($Databases.Count -eq 0) {
    Write-Error "Lista `$Databases este goala. Editeaza scriptul si adauga numele bazelor de date."
}

function Invoke-Step {
    param([string]$Description, [scriptblock]$Action)
    Write-Host "  -> $Description" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Pas esuat ($Description) - exit code $LASTEXITCODE"
    }
}

foreach ($db in $Databases) {
    Write-Host "==== $db ====" -ForegroundColor Yellow
    $archiveName   = "$db.gz"
    $containerPath = "/tmp/$archiveName"
    $localPath     = Join-Path $LocalDumpDir $archiveName

    Invoke-Step "mongodump (container) -> $containerPath" {
        docker exec $MongoContainer mongodump --db $db --archive=$containerPath --gzip
    }

    Invoke-Step "docker cp -> $localPath" {
        docker cp "${MongoContainer}:$containerPath" $localPath
    }

    Invoke-Step "scp -> ${RemoteUser}@${RemoteHost}:$RemoteHomeDir/$archiveName" {
        scp $localPath "${RemoteUser}@${RemoteHost}:$RemoteHomeDir/$archiveName"
    }

    $remoteCommand = "sudo cp $RemoteHomeDir/$archiveName $RemoteFinalDir/ && " +
                     "cd $RemoteFinalDir && " +
                     "mongorestore --archive=$RemoteFinalDir/$archiveName --gzip"

    Invoke-Step "ssh -> restore pe server" {
        ssh "${RemoteUser}@${RemoteHost}" $remoteCommand
    }

    Write-Host "  OK: $db restaurat pe server." -ForegroundColor Green
}

Write-Host "Gata. $($Databases.Count) baze de date sincronizate." -ForegroundColor Green
