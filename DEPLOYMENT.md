# MAAPS Deployment Pipeline Documentation

## Overview

The MAAPS deployment pipeline automates testing, building, scanning, and deploying the orchestrator and audio worker services across development, staging, and production environments.

**Pipeline Flow:**
```
Push to develop/main
    ↓
Test (pytest)
    ↓
Build & Push Images (Docker)
    ├─ Orchestrator image
    └─ Audio Worker image
    ↓
[develop branch] → Deploy to Staging
    ├─ SSH deploy
    ├─ Health checks
    └─ Smoke tests
    
[main branch] → Security Scan (Trivy)
    ↓
[main branch] → Deploy to Production
    ├─ Pre-deployment checks
    ├─ SSH deploy
    ├─ Health checks
    └─ Notify team
```

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Git

### Installation

1. **Clone and configure:**
   ```bash
   git clone https://github.com/your-org/maaps.git
   cd maaps
   cp .env.example .env
   ```

2. **Edit `.env` with your local values:**
   ```bash
   POSTGRES_USER=maaps
   POSTGRES_PASSWORD=dev_password
   QDRANT_API_KEY=dev_key
   ```

3. **Start services:**
   ```bash
   docker compose up -d
   ```

4. **Run tests:**
   ```bash
   python -m pytest tests/ -v
   ```

---

## GitHub Actions Workflow

### 1. Testing (`test` job)

**Trigger:** Every push and PR to `develop`/`main`

**Steps:**
- Checkout code
- Set up Python 3.11
- Install dependencies
- Run pytest with coverage
- Upload coverage to Codecov

**Exit on failure:** Yes — builds/deploys cannot proceed if tests fail.

### 2. Build & Push (`build-and-push` job)

**Trigger:** `git push` to `develop` or `main` (only on success of `test`)

**Builds:**
- Orchestrator image → `ghcr.io/your-org/maaps/orchestrator:latest`, `orchestrator:develop`, etc.
- Audio Worker image → `ghcr.io/your-org/maaps/audio_worker:latest`, `audio_worker:develop`, etc.

**Features:**
- Multi-stage Docker builds for optimization
- BuildKit cache enabled for faster rebuilds
- Images tagged with branch name, commit SHA, and version
- Latest tag applied to main branch

**Image Registry:** GitHub Container Registry (GHCR)

### 3. Security Scan (`security-scan` job)

**Trigger:** After successful build, only on `main` branch

**Scan Tool:** Trivy (aquasecurity)

**Scans:**
- Container image vulnerabilities
- Severity levels: CRITICAL, HIGH
- Results uploaded to GitHub Security tab (SARIF format)

### 4. Deploy to Staging (`deploy-staging` job)

**Trigger:** After successful build & push, only on `develop` branch

**Deployment:**
- SSH into staging server
- `git pull origin develop`
- `docker compose pull` (new images)
- `docker compose up -d` (restart services)

**Post-deployment:**
- Smoke test: `curl -f http://staging-url/health`

**Secrets Required:**
- `DEPLOY_KEY`: SSH private key (ED25519 recommended)
- `DEPLOY_HOST_STAGING`: Staging server hostname/IP
- `DEPLOY_USER_STAGING`: SSH user (e.g., `deploy`)
- `STAGING_URL`: Staging application URL (e.g., `http://staging.maaps.internal:8080`)

### 5. Deploy to Production (`deploy-production` job)

**Trigger:** After successful build, scan, & push, only on `main` branch

**Pre-deployment:**
- Create GitHub Deployment object (for tracking)
- Requires manual environment approval (optional but recommended)

**Deployment:**
- SSH into production server
- `git pull origin main`
- `docker compose pull`
- `docker compose down` (stop old containers)
- `docker compose up -d` (start new containers)
- Verify config loads: `docker compose exec -T orchestrator python -c "from core import Config; print('Config loaded')"`

**Post-deployment:**
- Health check loop (retry 30x over 5 minutes)
- Waits for `GET /health` to return 200
- Updates GitHub Deployment status

**Secrets Required:**
- `DEPLOY_KEY`: SSH private key
- `DEPLOY_HOST_PROD`: Production server hostname/IP
- `DEPLOY_USER_PROD`: SSH user
- `PROD_URL`: Production application URL
- `SLACK_WEBHOOK`: (Optional) Slack webhook for notifications

**Environment Protection:**
- Mark as protected environment in GitHub
- Requires branch protection rules
- Optional: require manual approval

### 6. Notifications (`notify` job)

**Trigger:** Always after test & build

**Channels:**
- Slack webhook on failure or success
- Includes workflow name, branch, author, run link

**Secrets Required:**
- `SLACK_WEBHOOK`: Slack incoming webhook URL

---

## Setup: GitHub Secrets

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

```
DEPLOY_KEY                 # SSH private key (base64 encoded or as file)
DEPLOY_HOST_STAGING       # staging.example.com
DEPLOY_USER_STAGING       # deploy
DEPLOY_HOST_PROD          # prod.example.com
DEPLOY_USER_PROD          # deploy
STAGING_URL               # http://staging.maaps.internal:8080
PROD_URL                  # https://maaps.example.com
SLACK_WEBHOOK             # https://hooks.slack.com/services/...
```

**SSH Key Setup:**

1. Generate ED25519 key (no passphrase):
   ```bash
   ssh-keygen -t ed25519 -f deploy_key -N ""
   ```

2. Copy public key to deployment servers:
   ```bash
   ssh-copy-id -i deploy_key.pub deploy@staging.example.com
   ssh-copy-id -i deploy_key.pub deploy@prod.example.com
   ```

3. Add private key as GitHub secret:
   ```bash
   cat deploy_key | base64 | pbcopy  # macOS
   # Paste into DEPLOY_KEY secret
   ```

---

## Setup: Deployment Servers

### Prerequisites per server

```bash
# Install Docker & Docker Compose
curl -fsSL https://get.docker.com | sh
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Add deploy user
sudo useradd -m -s /bin/bash deploy
sudo usermod -aG docker deploy
```

### Repository setup per server

```bash
# As deploy user
cd /opt
sudo git clone https://github.com/your-org/maaps.git
sudo chown -R deploy:deploy maaps

# Copy and configure environment
cd maaps
cp .env.example .env
nano .env  # Edit with production/staging values
```

### Login to container registry

```bash
# As deploy user
docker login ghcr.io
# Use personal access token with `read:packages` scope
```

---

## Kubernetes Deployment

For multi-node production environments, use Kubernetes:

```bash
# Deploy to cluster (default namespace)
kubectl apply -f k8s/maaps-deployment.yaml

# Check rollout status
kubectl rollout status deployment/orchestrator -n maaps

# View logs
kubectl logs -n maaps -l app=orchestrator -f

# Scale replicas
kubectl scale deployment orchestrator --replicas=3 -n maaps

# Upgrade images
kubectl set image deployment/orchestrator orchestrator=ghcr.io/your-org/maaps/orchestrator:v1.2.3 -n maaps
```

**Features:**
- 2 Orchestrator replicas with pod anti-affinity
- Horizontal Pod Autoscaler (CPU/memory based)
- ConfigMaps for non-sensitive environment variables
- Secrets for sensitive data (API keys, passwords)
- Persistent volumes for postgres, qdrant, models, local files
- Health checks (liveness & readiness probes)
- Resource requests and limits

**Requirements:**
- Kubernetes cluster (GKE, EKS, AKS, etc.)
- GPU node with `accelerator=nvidia-gpu` label (for audio worker)
- NVIDIA GPU Plugin for Kubernetes
- Nginx Ingress Controller
- Cert-manager for TLS (optional)

---

## Manual Deployment (SSH)

For simple single-host deployments:

```bash
# SSH to server
ssh deploy@prod.example.com

# Navigate to repo
cd /opt/maaps

# Pull latest code
git pull origin main

# Pull latest images
docker compose pull

# Restart services
docker compose down
docker compose up -d

# Verify health
curl http://localhost:8080/health
```

---

## Rollback Procedure

If deployment fails or issues arise:

```bash
# SSH to server
ssh deploy@prod.example.com
cd /opt/maaps

# Revert to previous commit
git reset --hard HEAD~1

# Pull old images
docker compose pull

# Restart
docker compose down
docker compose up -d

# Verify health
curl http://localhost:8080/health
```

Or redeploy a specific image tag:

```bash
# Edit docker-compose.yml to use specific image tag
nano docker-compose.yml

# Restart
docker compose down
docker compose pull
docker compose up -d
```

---

## Monitoring & Logs

### Container Logs

```bash
# Docker Compose
docker compose logs -f orchestrator
docker compose logs -f audio_worker

# Kubernetes
kubectl logs -n maaps -l app=orchestrator -f
kubectl logs -n maaps -l app=audio-worker -f
```

### Health Checks

```bash
# Local
curl http://localhost:8080/health

# Staging
curl http://staging.maaps.internal:8080/health

# Production
curl https://maaps.example.com/health
```

### Database Queries

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U maaps -d maaps

# List tables
\dt

# Check agent status
SELECT * FROM agents WHERE status = 'active';
```

### GPU Status (Audio Worker)

```bash
# Check GPU allocation
docker compose exec audio_worker nvidia-smi

# Monitor in Kubernetes
kubectl top nodes -l accelerator=nvidia-gpu
```

---

## Troubleshooting

### Build Failures

- **Rate limiting:** GitHub Actions runs multiple builds. Use specific base image versions.
- **Dependency conflicts:** Update requirements.txt and test locally first.
- **Cache issues:** Clear GitHub Actions cache in repo settings.

### Deployment Failures

- **SSH key permission denied:** Ensure correct permissions: `chmod 600 ~/.ssh/deploy_key`
- **Health check timeout:** Services may need more startup time. Increase probe thresholds.
- **Port already in use:** Stop competing services: `docker compose down`
- **Image pull errors:** Ensure container registry login credentials are valid.

### Runtime Issues

- **Out of memory:** Check resource limits in docker-compose.yml or k8s manifests.
- **PostgreSQL connection refused:** Verify `POSTGRES_HOST` and network connectivity.
- **Selenium timeout:** Increase `SE_NODE_SESSION_TIMEOUT` in docker-compose.yml.

---

## Best Practices

1. **Always test locally before pushing:**
   ```bash
   docker compose up -d
   pytest tests/ -v
   ```

2. **Use semantic versioning for tags:**
   - Main branch: `v1.2.3`, `latest`
   - Develop branch: `develop`, `develop-sha-abc123`

3. **Keep `.env.example` synchronized:**
   - Document all new environment variables
   - Never commit `.env` with secrets

4. **Monitor deployments:**
   - Set up Slack notifications
   - Check logs regularly
   - Monitor resource usage

5. **Practice rollback procedures:**
   - Test rollback process monthly
   - Keep at least 2 previous image versions available

6. **Secure deployment servers:**
   - Use firewall rules
   - Limit SSH access
   - Rotate deploy keys quarterly

---

## Support & Issues

For pipeline issues or questions:

1. Check GitHub Actions logs: Actions tab → workflow run → failed job
2. SSH to server and check service logs: `docker compose logs -f`
3. Review deployment server system logs: `journalctl -xe`
4. Test locally with same docker-compose.yml

---

**Last updated:** 2024
**Maintained by:** DevOps team
