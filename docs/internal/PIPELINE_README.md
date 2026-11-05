# MAAPS Deployment Pipeline

Complete CI/CD and deployment pipeline for the MAAPS Nexus system with Docker and GitHub Actions.

## 📋 What's Included

### Workflows (.github/workflows/)

1. **ci-cd.yml** - Main deployment pipeline
   - Test suite (pytest)
   - Docker image building (multi-stage, BuildKit optimized)
   - Container registry push (GHCR)
   - Staging deployment (develop branch)
   - Security scanning (Trivy)
   - Production deployment (main branch with approval)
   - Slack notifications

2. **security.yml** - Security scanning (weekly + on push)
   - Python dependency analysis (safety)
   - Dockerfile linting (hadolint)
   - Code quality checks (flake8, black, pylint)
   - Secret scanning (truffleHog)
   - SBOM generation (Syft)
   - Container image scanning (Grype)

### Kubernetes Manifests (k8s/)

- **maaps-deployment.yaml** - Complete K8s deployment:
  - Namespace isolation
  - ConfigMaps for environment variables
  - Secrets for sensitive data
  - Deployments: PostgreSQL, Qdrant, Audio Worker, Selenium, Orchestrator
  - Services: ClusterIP (internal) and LoadBalancer (external)
  - Ingress with TLS
  - Persistent volumes for data
  - Horizontal Pod Autoscaler for orchestrator
  - Resource requests and limits
  - Health checks (liveness & readiness probes)

### Deployment Files

- **docker-compose.staging.yml** - Staging overrides
- **.env.example** - Environment template (already exists, reference in docs)

### Scripts (scripts/)

1. **deploy.sh** - Automated deployment tool
   - Deploy to staging or production
   - Confirmation prompts
   - Local build and test before deploy
   - Health checks post-deployment
   - Rollback support
   - Error handling and logging

2. **monitor.sh** - Status monitoring
   - SSH connectivity check
   - Container status
   - Service health
   - Disk space
   - Database connectivity
   - Error log review
   - Git status

### Documentation

1. **DEPLOYMENT.md** (11KB)
   - Complete pipeline architecture
   - Job-by-job breakdown
   - GitHub secrets setup
   - Deployment server configuration
   - Kubernetes deployment guide
   - Manual deployment steps
   - Rollback procedures
   - Troubleshooting guide
   - Best practices

2. **DEPLOYMENT_QUICK_REF.md** (7KB)
   - Visual pipeline flow
   - Common tasks and commands
   - Environment configuration
   - Troubleshooting quick answers
   - Performance tips
   - Security checklist

3. **DEPLOYMENT_SETUP_CHECKLIST.md** (10KB)
   - 10-phase setup guide
   - Pre-deployment verification
   - Post-deployment validation
   - Section-by-section checklist

---

## 🚀 Quick Start

### 1. Enable GitHub Actions

```bash
# Push workflow files to repository
git add .github/workflows/ DEPLOYMENT*.md scripts/
git commit -m "Add CI/CD deployment pipeline"
git push origin main
```

### 2. Configure GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

```
DEPLOY_KEY              # SSH private key
DEPLOY_HOST_STAGING     # staging.example.com
DEPLOY_USER_STAGING     # deploy
DEPLOY_HOST_PROD        # prod.example.com
DEPLOY_USER_PROD        # deploy
STAGING_URL             # http://staging.internal:8080
PROD_URL                # https://maaps.example.com
SLACK_WEBHOOK           # (optional)
```

### 3. Set Up Deployment Servers

```bash
# SSH into staging server
ssh deploy@staging.example.com

# Install Docker & Docker Compose
curl -fsSL https://get.docker.com | sh
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Clone repository
cd /opt
sudo git clone https://github.com/your-org/maaps.git
sudo chown -R deploy:deploy maaps

# Configure environment
cd maaps
cp .env.example .env
# Edit .env with staging values
nano .env

# Login to container registry
docker login ghcr.io
# Use GitHub Personal Access Token
```

### 4. Deploy

```bash
# From develop branch → automatically deploys to staging
git checkout develop
git commit -m "Feature: add new capability"
git push origin develop

# GitHub Actions will automatically:
# ✓ Run tests
# ✓ Build images
# ✓ Push to registry
# ✓ Deploy to staging
# ✓ Run smoke tests

# From main branch → automatically deploys to production
# (after merge from develop)
git checkout main
git pull origin develop
git push origin main

# GitHub Actions will:
# ✓ Run tests
# ✓ Build images
# ✓ Security scan
# ✓ Deploy to production (with manual approval)
# ✓ Verify health
```

### 5. Monitor Deployment

```bash
# Watch GitHub Actions
open "https://github.com/your-org/maaps/actions"

# Or use monitoring script
./scripts/monitor.sh staging
./scripts/monitor.sh production
```

---

## 📊 Pipeline Flow

```
Commit → Test → Build → [Staging Deploy] + [Prod Security Scan]
                                ↓                      ↓
                          (develop branch)      [Prod Deploy]
                                                (main branch)
                                                      ↓
                                              Slack Notification
```

**Branches:**
- `develop` → Deploys to staging automatically
- `main` → Deploys to production automatically (after security scan)

---

## 🔍 What Gets Tested

### Automated Testing (Every Push)

- [ ] Python unit tests (pytest)
- [ ] Code coverage reporting
- [ ] Dockerfile linting
- [ ] Code quality (flake8, black, pylint)
- [ ] Secret detection
- [ ] Dependency vulnerabilities
- [ ] Container image vulnerabilities (CRITICAL, HIGH)

### Deployment Verification

- [ ] SSH connectivity
- [ ] Container health checks
- [ ] API health endpoints (`/health`)
- [ ] Database connectivity
- [ ] Configuration loading

---

## 📁 File Structure

```
.github/workflows/
├── ci-cd.yml              # Main pipeline
└── security.yml           # Security scanning

k8s/
└── maaps-deployment.yaml  # Kubernetes manifests

scripts/
├── deploy.sh              # Deployment tool
└── monitor.sh             # Status monitor

docker-compose.staging.yml # Staging overrides
DEPLOYMENT.md              # Full documentation
DEPLOYMENT_QUICK_REF.md    # Quick reference
DEPLOYMENT_SETUP_CHECKLIST.md  # Setup steps
```

---

## 🔑 Key Features

✅ **Multi-stage Docker builds** - Optimized image sizes
✅ **BuildKit caching** - Fast rebuilds
✅ **Automated testing** - No broken deploys
✅ **Security scanning** - Trivy, Grype, truffleHog
✅ **Staging environment** - Test before production
✅ **Health checks** - Verify deployments work
✅ **Rollback support** - Revert quickly if needed
✅ **Slack notifications** - Real-time alerts
✅ **Kubernetes ready** - Scale to multi-node
✅ **SSH deployment** - Simple single-server option
✅ **Auto-scaling** - HPA for orchestrator
✅ **Persistent volumes** - Data survives restarts

---

## 🛠️ Maintenance

### Update Dependencies

```bash
# Bump Python packages
pip install --upgrade -r requirements.txt
pip freeze > requirements.txt
git commit -am "Bump dependencies"
git push origin main
# Pipeline will rebuild and test automatically
```

### Rotate SSH Keys

```bash
# Generate new key
ssh-keygen -t ed25519 -f deploy_key_new -N ""

# Update deployment servers
ssh-copy-id -i deploy_key_new.pub deploy@prod.example.com

# Update GitHub secret
# (Replace DEPLOY_KEY with new key content)

# Remove old key from servers
ssh deploy@prod.example.com "cat >> ~/.ssh/authorized_keys" < deploy_key.pub
```

### Update Image Versions

Edit `docker-compose.yml` base images:

```yaml
orchestrator:
  build:
    args:
      PYTHON_VERSION: "3.12"  # Update here

audio_worker:
  build:
    args:
      PYTORCH_VERSION: "2.2.0"  # Update here
      CUDA_VERSION: "12.2"      # Update here
```

Then push to trigger rebuild:

```bash
git commit -am "Bump base image versions"
git push origin develop
# Test in staging first
```

---

## 🐛 Troubleshooting

### Deploy Failed?

1. Check logs: https://github.com/your-org/maaps/actions
2. SSH to server: `ssh deploy@staging.example.com`
3. Check containers: `docker compose ps`
4. Check logs: `docker compose logs -f orchestrator`

### Health Check Failed?

```bash
# Test locally
curl http://localhost:8080/health

# Test on server
ssh deploy@staging.example.com "curl http://localhost:8080/health"

# Check app logs
docker compose logs orchestrator | grep -i error
```

### Secrets Not Working?

```bash
# Verify secrets are added to GitHub
# Settings → Secrets and variables → Actions

# Check they're used in workflow
# View: .github/workflows/ci-cd.yml

# Test SSH key works
ssh -i ~/.ssh/deploy_key deploy@staging.example.com "echo Connected"
```

See **DEPLOYMENT.md** for detailed troubleshooting.

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| **DEPLOYMENT.md** | Complete pipeline guide (11KB) |
| **DEPLOYMENT_QUICK_REF.md** | Quick commands reference (7KB) |
| **DEPLOYMENT_SETUP_CHECKLIST.md** | Setup steps (10KB) |
| **scripts/deploy.sh** | Automated deployment tool |
| **scripts/monitor.sh** | Status monitoring tool |

---

## 🔐 Security Considerations

- ✅ Non-root containers (already configured)
- ✅ Secret scanning in CI/CD
- ✅ Container image vulnerability scanning
- ✅ Secrets stored in GitHub (not in code)
- ✅ Branch protection rules
- ✅ SSH key-based authentication
- ✅ Health checks prevent bad deploys

**Recommended additions:**
- Network policies in Kubernetes
- Pod security policies
- Encryption at rest for databases
- VPN access to production
- Audit logging

See **DEPLOYMENT.md** for security hardening checklist.

---

## 📞 Support

For issues or questions:

1. Check **DEPLOYMENT_QUICK_REF.md** for quick answers
2. Review **DEPLOYMENT.md** troubleshooting section
3. Check GitHub Actions logs
4. SSH to server and inspect logs

---

## 📝 License

This deployment pipeline is provided as-is for MAAPS project use.

---

**Version:** 1.0  
**Last Updated:** 2024  
**Maintained by:** DevOps Team

**Quick Links:**
- [Full Documentation](./DEPLOYMENT.md)
- [Quick Reference](./DEPLOYMENT_QUICK_REF.md)
- [Setup Checklist](./DEPLOYMENT_SETUP_CHECKLIST.md)
- [GitHub Actions](https://github.com/your-org/maaps/actions)
