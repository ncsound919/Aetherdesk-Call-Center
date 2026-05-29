@echo off
REM AetherDesk Call Center - GKE Deployment Script
REM Prerequisites: kubectl, GKE cluster running, gcloud authenticated

echo ========================================
echo  AetherDesk Call Center - GKE Deploy
echo  Domain: aetherdesk.com
echo ========================================
echo.

REM Check kubectl
kubectl version --client >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: kubectl not found. Download from: https://dl.k8s.io/release/v1.28.0/bin/windows/amd64/kubectl.exe
    exit /b 1
)

REM Check cluster connection
kubectl cluster-info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Cannot connect to GKE cluster.
    echo Run: gcloud container clusters get-credentials aetherdesk_cluster --region us-east1 --project YOUR_PROJECT_ID
    exit /b 1
)

echo Deploying infrastructure...

REM Step 1: Create namespace
kubectl apply -f kubernetes\namespace.yaml
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to create namespace
    exit /b 1
)

REM Step 2: Deploy config and secrets
kubectl apply -f kubernetes\configmap.yml
echo.
echo NOTE: Before proceeding, update kubernetes\deployment.yml with real secrets:
echo   - DB_PASSWORD
echo   - SIP_TRUNK_PASSWORD (from Fondster)
echo   - ENCRYPTION_KEY (run: python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())")
echo   - JWT_SECRET
echo   - FS_ESL_PASSWORD
echo.

REM Step 3: Deploy core infrastructure
kubectl apply -f kubernetes\deployment.yml
kubectl apply -f kubernetes\services.yml

REM Step 4: Deploy SSL/TLS (requires cert-manager)
echo Installing cert-manager for SSL...
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.4/cert-manager.yaml
echo Waiting for cert-manager to be ready...
kubectl wait --for=condition=Available --timeout=120s -n cert-manager deployment/cert-manager-webhook
kubectl apply -f kubernetes\ssl.yml

REM Step 5: Deploy monitoring
kubectl apply -f kubernetes\monitoring.yml

REM Step 6: Deploy backup
kubectl apply -f kubernetes\backup.yml

echo.
echo ========================================
echo  Deployment Complete!
echo ========================================
echo.
echo  API:  https://api.aetherdesk.com
echo  App:  https://app.aetherdesk.com
echo.
echo  Check status: kubectl get pods -n aetherdesk
echo  Check logs:   kubectl logs -n aetherdesk deployment/aetherdesk-api
echo  View all:     kubectl get all -n aetherdesk
echo.
echo  DNS Setup:
echo    api.aetherdesk.com A -^> LoadBalancer IP
echo    app.aetherdesk.com A -^> LoadBalancer IP
echo.
