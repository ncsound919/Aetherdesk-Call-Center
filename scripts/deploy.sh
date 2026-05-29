#!/bin/bash
# AetherDesk Call Center - Deployment Script
# Usage: ./deploy.sh [dev|staging|production]

set -e

ENVIRONMENT=${1:-dev}
PROJECT_ID="aetherdesk"
CLUSTER_NAME="aetherdesk-cluster"
REGION="us-east1"

echo "========================================"
echo "AetherDesk Call Center Deployment"
echo "Environment: $ENVIRONMENT"
echo "========================================"

# Check prerequisites
echo ""
echo "[1/10] Checking prerequisites..."
command -v gcloud >/dev/null 2>&1 || { echo "gcloud CLI not found. Please install it first."; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found. Please install it first."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Docker not found. Please install it first."; exit 1; }

# Authenticate with GCP
echo ""
echo "[2/10] Authenticating with Google Cloud..."
gcloud auth login --quiet 2>/dev/null || echo "Please authenticate in the browser..."
gcloud config set project $PROJECT_ID

# Get GKE credentials
echo ""
echo "[3/10] Getting GKE cluster credentials..."

# Build Docker images
echo ""
echo "[4/10] Building Docker images..."

# Push images to GCR
echo ""
echo "[5/10] Pushing images to Google Container Registry..."
docker push gcr.io/$PROJECT_ID/aetherdesk-api:latest
docker push gcr.io/$PROJECT_ID/aetherdesk-ui:latest

# Create GPU node pool
echo ""
echo "[6/10] Creating GPU node pool..."
gcloud container node-pools create aetherdesk-gpu-nodepool \
  --cluster=$CLUSTER_NAME \
  --region=$REGION \
  --machine-type=n1-standard-4 \
  --num-nodes=1 \
  --accelerator=type=nvidia-t4-vmware-gpu,count=1 \
  --node-labels=workload-type=gpu-ai \
  --node-taints=nvidia.com/gpu=present:NoSchedule \
  --project=$PROJECT_ID 2>/dev/null || echo "GPU node pool may already exist"

# Create CPU node pool for TTS
echo ""
echo "[7/10] Creating CPU node pool..."
gcloud container node-pools create aetherdesk-cpu-nodepool \
  --cluster=$CLUSTER_NAME \
  --region=$REGION \
  --machine-type=n2-standard-4 \
  --num-nodes=2 \
  --node-labels=workload-type=cpu-ai \
  --project=$PROJECT_ID 2>/dev/null || echo "CPU node pool may already exist"

# Apply Kubernetes manifests
echo ""
echo "[8/10] Applying Kubernetes manifests..."
kubectl apply -f kubernetes/namespace.yaml --recursive

# Apply ConfigMaps and Secrets
echo ""
echo "[9/10] Creating ConfigMaps and Secrets..."
kubectl create secret generic aetherdesk-secrets \
  --from-literal=DB_PASSWORD="$DB_PASSWORD" \
  --from-literal=REDIS_PASSWORD="$REDIS_PASSWORD" \
  --from-literal=FONOSTER_API_KEY="$FONOSTER_API_KEY" \
  --from-literal=FONOSTER_API_SECRET="$FONOSTER_API_SECRET" \
  --from-literal=ENCRYPTION_KEY="$ENCRYPTION_KEY" \
  --from-literal=JWT_SECRET="$JWT_SECRET" \
  --from-literal=DEEPGRAM_API_KEY="$DEEPGRAM_API_KEY" \
  --from-literal=GROQ_API_KEY="$GROQ_API_KEY" \
  --from-literal=SIP_TRUNK_PASSWORD="$SIP_TRUNK_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

# Apply main deployment
echo ""
echo "[10/10] Deploying application..."
kubectl apply -f kubernetes/deployment.yml --recursive

# Wait for deployments to be ready
echo ""
echo "Waiting for deployments to be ready..."
kubectl rollout status deployment/aetherdesk-api -n aetherdesk --timeout=300s
kubectl rollout status deployment/aetherdesk-fonoster -n aetherdesk --timeout=300s
kubectl rollout status deployment/aetherdesk-freeswitch -n aetherdesk --timeout=300s

echo ""
echo "========================================"
echo "Deployment complete!"
echo "========================================"
echo ""
echo "Get service URLs:"
echo "  API: $(kubectl get service aetherdesk-api -n aetherdesk -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"
echo "  Fonster: $(kubectl get service aetherdesk-fonoster -n aetherdesk -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"
echo "  FreeSWITCH SIP: $(kubectl get service aetherdesk-freeswitch-sip -n aetherdesk -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"