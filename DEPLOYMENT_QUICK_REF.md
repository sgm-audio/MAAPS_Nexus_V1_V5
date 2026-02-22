# Deployment Quick Reference

## Pipeline at a Glance

```
Commit pushed
  ↓
Test (pytest) ─ Fails? → Fix & push again
  ↓ ✓
Build & Push images to GHCR
  ├─ Orchestrator
  └─ Audio Worker
  ↓
[If develop branch]
  ↓
Deploy to Staging
  ├─ SSH into staging server
  ├─ Pull code & images
  ├─ Restart containers
  └─ Health check
  ↓
[If main branch]
  ↓
Security Scan (Trivy)
  ├─ Scan images for vulnerabilities
  └─ Report to GitHub Security
  ↓
Deploy to Production (manual approval optional)
  ├─ Create deployment object
  ├─ SSH into production
  ├─ Pull code & images
  ├─ Restart containers
  ├─ Verify configuration
  └─ Health check loop
  ↓
Notify Slack (success or failure)
```

---

## Common Tasks

### Check Deployment Status

```bash
# View latest workflow run
open "https://github.com/your-org/maaps/actions"

# Or use monitoring script
./scripts/monitor.sh staging
./scripts/monitor.sh production
```

### Deploy Manually (Skip GitHub Actions)

```bash
# To staging
./scripts/deploy.sh staging

# To production (requires --force)
./scripts/deploy.sh production --force
```

### View Logs

```bash
# Docker Compose (local or remote via SSH)
docker compose logs -f orchestrator
docker compose logs -f audio_worker
docker compose logs -f postgres

# Kubernetes
kubectl logs -n maaps -l app=orchestrator -f
kubectl logs -n maaps -l app=audio_worker -f
```

### Rollback Deployment

```bash
# Quick rollback script
./scripts/deploy.sh staging --rollback
./scripts/deploy.sh production --rollback

# Manual rollback
ssh deploy@prod.example.com
cd /opt/maaps
git reset --hard HEAD~1
docker compose down
docker compose pull
docker compose up -d
```

### Check Service Health

```bash
# Orchestrator
curl http://localhost:8080/health
curl https://maaps.example.com/health

# Audio Worker
curl http://localhost:8000/health

# PostgreSQL
docker compose exec postgres pg_isready -U maaps -d maaps

# Qdrant
curl http://localhost:6333/health
```

### Scale Services (Kubernetes)

```bash
# Scale orchestrator to 3 replicas
kubectl scale deployment orchestrator --replicas=3 -n maaps

# View auto-scaling status
kubectl get hpa -n maaps
```

### Update Environment Variables

```bash
# Docker Compose
1. Edit .env file
2. docker compose down
3. docker compose up -d

# Kubernetes
1. Edit secret: kubectl edit secret maaps-secrets -n maaps
2. Restart pods: kubectl rollout restart deployment/orchestrator -n maaps
```

### View Image Details

```bash
# Get current image tag running
docker compose images
kubectl get deployment orchestrator -n maaps -o jsonpath='{.spec.template.spec.containers[0].image}'

# View image history
docker history ghcr.io/your-org/maaps/orchestrator:latest
```

---

## Environment Configuration

### GitHub Secrets Required

```
DEPLOY_KEY              # SSH private key
DEPLOY_HOST_STAGING     # staging server
DEPLOY_USER_STAGING     # SSH user
DEPLOY_HOST_PROD        # prod server
DEPLOY_USER_PROD        # SSH user
STAGING_URL             # http://staging.internal:8080
PROD_URL                # https://maaps.example.com
SLACK_WEBHOOK           # (optional)
```

### .env File Variables

```bash
# Database
POSTGRES_USER=maaps
POSTGRES_PASSWORD=<secret>
POSTGRES_DB=maaps

# Vector DB
QDRANT_API_KEY=<secret>

# APIs
HEARTMULA_API_KEY=<optional>
ELEVENLABS_API_KEY=<optional>
GITHUB_WEBHOOK_SECRET=<optional>

# Deployment
TZ=UTC
```

---

## Troubleshooting

### "Build failed: image pull rate limit"

**Solution:** Specify exact base image versions:
```dockerfile
FROM python:3.11.7-slim-bookworm  # Instead of :3.11-slim
FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-runtime
```

### "Health check failed after deployment"

**Check logs:**
```bash
docker compose logs -f orchestrator
```

**Common causes:**
- Database not ready yet (increase timeout)
- Config not loaded (check environment variables)
- Port already in use (stop competing services)

### "SSH permission denied"

**Fix:**
```bash
# Verify key permissions
ls -la ~/.ssh/deploy_key  # Should be 600
chmod 600 ~/.ssh/deploy_key

# Test SSH
ssh -i ~/.ssh/deploy_key deploy@prod.example.com
```

### "PostgreSQL connection refused"

**Check:**
```bash
docker compose logs postgres
docker compose exec postgres pg_isready -U maaps

# If not running
docker compose up -d postgres
```

### "Out of memory"

**Check usage:**
```bash
docker compose stats
docker system df
```

**Increase limits in docker-compose.yml:**
```yaml
orchestrator:
  deploy:
    resources:
      limits:
        memory: 2G  # Increase from 1G
```

---

## Performance Tips

1. **Use BuildKit cache:**
   - Docker automatically uses BuildKit with GitHub Actions
   - For local: `DOCKER_BUILDKIT=1 docker build ...`

2. **Minimize image size:**
   - Use multi-stage builds (already done)
   - Use `.dockerignore` to exclude unnecessary files
   - Use slim/alpine base images

3. **Optimize layer caching:**
   - Put least-changing instructions first
   - Install dependencies before copying code
   - Already optimized in provided Dockerfiles

4. **Parallel deployments:**
   - GitHub Actions matrix builds both images simultaneously
   - Kubernetes can run multiple orchestrator replicas

---

## Monitoring & Alerts

### Set up Slack notifications:

1. Create incoming webhook: https://api.slack.com/messaging/webhooks
2. Copy webhook URL
3. Add as GitHub secret: `SLACK_WEBHOOK`

### GitHub Status Checks:

Enable branch protection rules (Repo Settings → Branches):
- Require passing of all status checks
- Require reviews before merge (optional)
- Automatically dismiss stale reviews

### Container Logs Rotation:

Already configured in docker-compose.yml:
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"      # Max 10MB per file
    max-file: "3"        # Keep 3 files (30MB total)
```

---

## Security Checklist

- [ ] SSH keys rotated within last 90 days
- [ ] Container registry credentials updated
- [ ] Trivy scans passing (no CRITICAL/HIGH vulns)
- [ ] Dependency updates reviewed
- [ ] Secrets not committed to git
- [ ] Branch protection rules enabled
- [ ] Deployment logs reviewed for errors
- [ ] Database backups verified
- [ ] Firewall rules restrict SSH access
- [ ] Non-root user running containers

---

## Links & Resources

- GitHub Actions: https://github.com/your-org/maaps/actions
- Container Registry: https://github.com/your-org/maaps/pkgs/container
- Kubernetes Dashboard: (configured per cluster)
- Docker Docs: https://docs.docker.com/
- GitHub Docs: https://docs.github.com/

---

**Last Updated:** 2024
**Quick Reference v1.0**
