# C:\Proyectos\visa\run_visa.ps1
$ErrorActionPreference = "Stop"

# Carpeta de trabajo y logs
Set-Location "C:\Proyectos\visa"
$logDir = "C:\Proyectos\visa\logs"
New-Item -ItemType Directory -Path $logDir -ErrorAction SilentlyContinue | Out-Null
$log = Join-Path $logDir ("visa-" + (Get-Date -f yyyyMMdd-HHmmss) + ".log")

# Ejecuta con el launcher de Python (py)
# Si necesitas variables de entorno, setéalas antes de la llamada:
# $env:AIS_USER="..."
# $env:AIS_PASS="..."

# Salida a log (stdout+stderr)
& py ".\visa_reprogram.py" *> $log
