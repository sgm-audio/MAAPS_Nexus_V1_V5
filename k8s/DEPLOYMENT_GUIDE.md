# MAAPS Kubernetes Deployment Guide

This guide explains how to deploy the MAAPS system to Kubernetes.

## Prerequisites

- Kubernetes cluster 1.20+
- `kubectl` configured to access your cluster
- For GPU workers: NVIDIA GPU nodes with proper drivers and nvidia-k8s-device-plugin installed
- For Ingress: NGINX Ingress Controller installed
- For TLS: cert-manager installed (optional)

## Quick Start

### 1. Prepare Your Environment

```bash
# Set your image registry and domain
export REGISTRY="ghcr.io/your-org"
export DOMAIN="maaps.example.com"
```

### 2. Update Manifest Values

Replace placeholder values in the manifests:

**03-secrets.yaml:**
- `POSTGRES_PASSWORD`: Strong password for database
- `QDRANT_API_KEY`: API key for vector database
- `HEARTMULA_API_KEY`: If using HeartMuLa cloud service
- `ELEVENLABS_API_KEY`: If using ElevenLabs
- `GITHUB_WEBHOOK_SECRET`: For GitHub CI/CD
- `SMTP_*`: Email configuration

**09-orchestrator.yaml & 07-audio-worker.yaml:**
- Replace `ghcr.io/your-org` with your actual image registry

**10-ingress.yaml:**
- Replace `maaps.example.com` with your domain

### 3. Create Namespace and Apply Manifests

Deploy in order:

```bash
# Apply namespace and storage configuration
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-storage-class.yaml

# Apply configuration (ConfigMap, Secrets, PVCs)
kubectl apply -f k8s/02-configmap.yaml
kubectl apply -f k8s/03-secrets.yaml
kubectl apply -f k8s/04-pvc.yaml

# Apply database and vector store
kubectl apply -f k8s/05-postgres.yaml
kubectl apply -f k8s/06-qdrant.yaml

# Wait for postgres and qdrant to be ready
kubectl wait --for=condition=ready pod -l app=postgres -n maaps --timeout=300s
kubectl wait --for=condition=ready pod -l app=qdrant -n maaps --timeout=300s

# Apply other services
kubectl apply -f k8s/08-selenium.yaml

# For GPU nodes, apply audio-worker
kubectl apply -f k8s/07-audio-worker.yaml

# Apply main orchestrator
kubectl apply -f k8s/09-orchestrator.yaml

# Apply ingress and network policies
kubectl apply -f k8s/10-ingress.yaml
kubectl apply -f k8s/11-network-policy.yaml
```

Or deploy all at once:

```bash
kubectl apply -f k8s/
```

### 4. Verify Deployment

```bash
# Check pod status
kubectl get pods -n maaps

# Check service status
kubectl get svc -n maaps

# Check persistent volumes
kubectl get pvc -n maaps

# View logs for a pod
kubectl logs -f deployment/orchestrator -n maaps

# Describe a deployment for events
kubectl describe deployment orchestrator -n maaps
```

### 5. Access the Application

**Via Service LoadBalancer** (if your cluster supports it):
```bash
kubectl get svc orchestrator -n maaps
# Use the EXTERNAL-IP:8080
```

**Via Ingress** (requires NGINX Ingress Controller):
```bash
# Update your /etc/hosts or DNS
echo "$(kubectl get ingress orchestrator-ingress -n maaps -o jsonpath='{.status.loadBalancer.ingress[0].ip}') maaps.example.com" | sudo tee -a /etc/hosts

# Access via browser
curl http://maaps.example.com
```

**Via Port-Forward** (for testing):
```bash
kubectl port-forward svc/orchestrator 8080:8080 -n maaps
# Access at http://localhost:8080
```

## Scaling

### Orchestrator Horizontal Autoscaling

Autoscaling is configured in `09-orchestrator.yaml` via HorizontalPodAutoscaler:
- **Min replicas**: 2
- **Max replicas**: 5
- **Triggers**: 70% CPU or 80% memory

Monitor autoscaling:
```bash
kubectl get hpa orchestrator-hpa -n maaps -w
```

### Manual Scaling

Scale any deployment manually:
```bash
# Scale orchestrator to 3 replicas
kubectl scale deployment orchestrator --replicas=3 -n maaps

# Scale audio-worker to 2 replicas (GPU permitting)
kubectl scale deployment audio-worker --replicas=2 -n maaps
```

## Storage

### Understanding PVCs

| Component | Size | Access Mode | Purpose |
|-----------|------|-------------|---------|
| postgres-pvc | 20Gi | RWO | Database data |
| qdrant-pvc | 50Gi | RWO | Vector embeddings |
| models-pvc | 100Gi | RWO | ML models (Demucs, etc.) |
| local-files-pvc | 50Gi | RWM | Input/output files |

**RWO** = ReadWriteOnce (single pod)
**RWM** = ReadWriteMany (multiple pods)

### Backup Strategy

```bash
# Backup postgres data
kubectl exec -it pod/postgres-xxxx -n maaps -- pg_dump -U maaps maaps > backup.sql

# Backup qdrant data
kubectl cp maaps/qdrant-xxxx:/qdrant/storage ./qdrant-backup
```

## Troubleshooting

### Pod not starting
```bash
# Check pod status
kubectl describe pod <pod-name> -n maaps

# Check logs
kubectl logs -f pod/<pod-name> -n maaps
```

### Persistent volume issues
```bash
# List PVCs
kubectl get pvc -n maaps

# Check PV status
kubectl get pv

# Describe a PVC for events
kubectl describe pvc postgres-pvc -n maaps
```

### Network connectivity issues
```bash
# Test DNS from a pod
kubectl run -it --rm debug --image=busybox --restart=Never -n maaps -- nslookup postgres.maaps.svc.cluster.local

# Test service connectivity
kubectl run -it --rm debug --image=busybox --restart=Never -n maaps -- wget http://orchestrator.maaps.svc.cluster.local:8080/health
```

### Database connection issues
```bash
# Check postgres pod logs
kubectl logs -f deployment/postgres -n maaps

# Connect to postgres from another pod
kubectl run -it --rm pg-client --image=postgres:16-alpine --restart=Never -n maaps -- \
  psql -h postgres.maaps.svc.cluster.local -U maaps -d maaps -c "SELECT version();"
```

### GPU issues (audio-worker)
```bash
# Check GPU availability on nodes
kubectl get nodes -L accelerator

# Verify GPU resources on a node
kubectl describe node <gpu-node-name>

# Check audio-worker pod for GPU
kubectl describe pod <audio-worker-pod-name> -n maaps
```

## Secrets Management

### Using Sealed Secrets (Recommended for Production)

Install Sealed Secrets controller:
```bash
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.18.0/controller.yaml -n kube-system
```

Seal secrets:
```bash
# Create a secret
kubectl create secret generic maaps-secrets \
  --from-literal=POSTGRES_PASSWORD=yourpassword \
  --from-literal=QDRANT_API_KEY=yourkey \
  -n maaps -o yaml > secrets.yaml

# Seal it
kubeseal -f secrets.yaml -w sealed-secrets.yaml

# Apply sealed secrets
kubectl apply -f sealed-secrets.yaml
```

### Using External Secret Manager

For AWS Secrets Manager, Azure Key Vault, or HashiCorp Vault integration, use ExternalSecrets Operator:
https://external-secrets.io/

## Monitoring and Logging

### Prometheus Metrics

Add Prometheus ServiceMonitor (requires Prometheus Operator):
```bash
kubectl apply -f k8s/12-prometheus-servicemonitor.yaml
```

### View Logs

```bash
# Real-time logs
kubectl logs -f deployment/orchestrator -n maaps

# Last 100 lines
kubectl logs -n maaps deployment/orchestrator --tail=100

# Logs from all containers in namespace
kubectl logs -n maaps -l app=orchestrator --all-containers=true
```

### Resource Usage

```bash
# View current resource usage
kubectl top pods -n maaps
kubectl top nodes

# Watch real-time usage
kubectl top pods -n maaps -w
```

## Updates and Upgrades

### Rolling Update

Update container image:
```bash
kubectl set image deployment/orchestrator \
  orchestrator=ghcr.io/your-org/maaps/orchestrator:v2.0.0 \
  -n maaps
```

### Rollback

```bash
# Check rollout history
kubectl rollout history deployment/orchestrator -n maaps

# Rollback to previous version
kubectl rollout undo deployment/orchestrator -n maaps

# Rollback to specific revision
kubectl rollout undo deployment/orchestrator --to-revision=2 -n maaps
```

## Network Policies

Network policies in `11-network-policy.yaml` restrict pod communication:
- Default: All ingress traffic denied
- Specific allow rules for each service

To disable network policies:
```bash
kubectl delete -f k8s/11-network-policy.yaml
```

## Cleanup

Remove all MAAPS resources:
```bash
# Delete all manifests
kubectl delete -f k8s/ -n maaps

# Delete namespace (removes all resources in it)
kubectl delete namespace maaps

# Delete persistent volumes manually if needed
kubectl delete pvc --all -n maaps
```

## Production Checklist

- [ ] Update all secrets in `03-secrets.yaml`
- [ ] Configure SMTP for email notifications
- [ ] Set up persistent volume backups
- [ ] Install and configure Prometheus/Grafana for monitoring
- [ ] Set resource requests/limits appropriately
- [ ] Enable network policies
- [ ] Configure RBAC for least privilege
- [ ] Set up ingress with TLS/HTTPS
- [ ] Configure log aggregation (ELK, Loki, etc.)
- [ ] Test disaster recovery procedures
- [ ] Document custom configurations
- [ ] Monitor costs (especially for GPU nodes)

## Support

For issues or questions:
1. Check pod logs: `kubectl logs -f <pod> -n maaps`
2. Describe resources: `kubectl describe pod <pod> -n maaps`
3. Check events: `kubectl get events -n maaps`
4. Review the main application documentation
