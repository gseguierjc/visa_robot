param(
    [switch]$UseCompose
)

# Intenta usar docker-compose si se indica o si está disponible
if ($UseCompose) {
    Write-Host "Construyendo y ejecutando con docker-compose..."
    docker compose up --build --remove-orphans
    exit $LastExitCode
}

Write-Host "Construyendo imagen docker..."
docker build -t visa_robot:local .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Ejecutando contenedor (se puede pasar AIS_USER/AIS_PASS como variables de entorno)..."
# Si existe .env, docker run usará las variables si hacemos --env-file .env
if (Test-Path .env) {
    docker run --rm --env-file .env -v ${PWD}\logs:/app/logs visa_robot:local
} else {
    Write-Host "No se encontró .env. Ejecuta: .\run_container.ps1 -UseCompose o pasa variables AIS_USER/AIS_PASS al invocar docker run."
    docker run --rm -e AIS_USER="tu_email" -e AIS_PASS="tu_password" -v ${PWD}\logs:/app/logs visa_robot:local
}