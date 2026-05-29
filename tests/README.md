# AetherDesk E2E Tests

## Setup Playwright

```bash
# Install Playwright browsers
playwright install chromium

# Install dependencies
pip install -r requirements.txt
```

## Run Tests

### GPU Node Pool Setup
```bash
# Set GCP project
set GCP_PROJECT_ID=aetherdesk

# Run GPU node pool test
pytest tests/e2e/gke_gpu_setup_test.py::test_gke_enable_gpu_nodepool -v
```

### CPU Node Pool Setup (for TTS)
```bash
pytest tests/e2e/gke_gpu_setup_test.py::test_gke_enable_cpu_nodepool -v
```

### Both Node Pools
```bash
pytest tests/e2e/gke_gpu_setup_test.py -v
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT_ID` | `aetherdesk` | GCP project ID |
| `GKE_CLUSTER_NAME` | `aetherdesk_cluster` | GKE cluster name |
| `GKE_REGION` | `us-east1` | GKE region |

## Test Flow

### GPU Node Pool
1. Navigate to GKE Clusters in Console
2. Click on cluster `aetherdesk_cluster`
3. Go to Node Pools tab
4. Click "Add Node Pool"
5. Configure:
   - Name: `aetherdesk-gpu-nodepool`
   - Machine: `n1-standard-4`
   - GPU: NVIDIA T4 (1 GPU)
   - Labels: `workload-type=gpu-ai`
   - Taints: `nvidia.com/gpu=present:NoSchedule`
6. Click Create

### CPU Node Pool (for TTS)
1. Same as above but:
   - Name: `aetherdesk-cpu-nodepool`
   - Machine: `n2-standard-4`
   - Nodes: 2
   - Labels: `workload-type=cpu-ai`