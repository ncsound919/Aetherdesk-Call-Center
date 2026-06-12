# Generate SealedSecret encrypted values using kubeseal
# Prerequisites: kubeseal installed, kubectl configured for GKE cluster
# Usage: .\scripts\generate-sealed-secret.ps1 -EnvFile .env
param(
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

# Check prerequisites
if (-not (Get-Command kubeseal -ErrorAction SilentlyContinue)) {
    Write-Error "kubeseal not found. Install: choco install kubeseal OR https://github.com/bitnami-labs/sealed-secrets/releases"
    exit 1
}

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Error "kubectl not found."
    exit 1
}

# Verify cluster connection and SealedSecrets controller
Write-Host "Checking GKE cluster connection..." -ForegroundColor Cyan
$clusterCheck = kubectl get nodes 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Cannot connect to Kubernetes cluster. Ensure kubectl is configured for your GKE cluster."
    exit 1
}
Write-Host "  Connected to cluster." -ForegroundColor Green

Write-Host "Checking SealedSecrets controller..." -ForegroundColor Cyan
$controllerCheck = kubectl get pods -n kube-system -l name=sealed-secrets-controller 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "SealedSecrets controller not found. Install: helm install sealed-secrets sealed-secrets/sealed-secrets -n kube-system"
    exit 1
}
Write-Host "  SealedSecrets controller is running." -ForegroundColor Green

# Load .env
if (-not (Test-Path $EnvFile)) {
    Write-Error ".env file not found at $EnvFile"
    exit 1
}

Write-Host "`nLoading secrets from $EnvFile..." -ForegroundColor Cyan
$secrets = @{}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $parts = $line.Split('=', 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value -and $value -notmatch '^(your-|REPLACE_WITH|REPLACE_ME|PASTE_)') {
            $secrets[$key] = $value
        }
    }
}

# Define secrets to seal
$secretKeys = @(
    "DB_PASSWORD",
    "REDIS_PASSWORD",
    "FONOSTER_API_KEY",
    "FONOSTER_API_SECRET",
    "ENCRYPTION_KEY",
    "JWT_SECRET",
    "WEBSOCKET_SECRET_KEY",
    "DEEPGRAM_API_KEY",
    "GROQ_API_KEY",
    "SIP_TRUNK_PASSWORD",
    "FS_ESL_PASSWORD"
)

# Create Kubernetes secret YAML from .env values
Write-Host "`nGenerating sealed secret..." -ForegroundColor Cyan
$kubectlArgs = @(
    "create", "secret", "generic", "aetherdesk-secrets",
    "-n", "aetherdesk",
    "--dry-run=client",
    "-o", "yaml"
)

foreach ($key in $secretKeys) {
    $val = $secrets[$key]
    if (-not $val) {
        Write-Warning "  $key not found in .env - skipping"
        continue
    }
    $kubectlArgs += "--from-literal=$key=$val"
}

# Pipe to kubeseal
$kubectlArgs += "--save-config"
$sealedYaml = & kubectl @kubectlArgs 2>&1 | kubeseal --format yaml --merge-into kubernetes\deployment.yml 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Error "kubeseal failed: $sealedYaml"
    exit 1
}

Write-Host "  SealedSecret values generated and merged into kubernetes/deployment.yml" -ForegroundColor Green
Write-Host "`nVerify with: kubectl apply -f kubernetes/deployment.yml --dry-run=server" -ForegroundColor Yellow
Write-Host "Deploy with:  kubectl apply -f kubernetes/deployment.yml" -ForegroundColor Yellow
