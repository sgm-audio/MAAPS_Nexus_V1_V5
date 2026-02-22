# Deployment Pipeline Setup Checklist

## Phase 1: Local Development Setup

- [ ] Clone repository
- [ ] Copy `.env.example` to `.env`
- [ ] Fill in local environment variables
- [ ] Run `docker compose up -d`
- [ ] Verify services: `docker compose ps`
- [ ] Run tests: `pytest tests/ -v`
- [ ] Test local deployments with `./scripts/deploy.sh staging`

## Phase 2: GitHub Repository Configuration

### Secrets Setup

- [ ] Generate SSH ED25519 key pair (no passphrase):
  ```bash
  ssh-keygen -t ed25519 -f deploy_key -N ""
  ```

- [ ] Create staging deployment server user:
  ```bash
  ssh-copy-id -i deploy_key.pub deploy@staging.example.com
  ```

- [ ] Create production deployment server user:
  ```bash
  ssh-copy-id -i deploy_key.pub deploy@prod.example.com
  ```

- [ ] Add GitHub Secrets (Settings → Secrets and variables → Actions):
  - [ ] `DEPLOY_KEY` = content of `deploy_key` (base64 encoded)
  - [ ] `DEPLOY_HOST_STAGING` = staging server hostname
  - [ ] `DEPLOY_USER_STAGING` = deploy user name
  - [ ] `DEPLOY_HOST_PROD` = production server hostname
  - [ ] `DEPLOY_USER_PROD` = deploy user name
  - [ ] `STAGING_URL` = http://staging.internal:8080
  - [ ] `PROD_URL` = https://maaps.example.com
  - [ ] `SLACK_WEBHOOK` = (optional) Slack webhook URL

### Container Registry

- [ ] Enable GitHub Container Registry (GHCR):
  - [ ] Go to Repository Settings → Actions → General
  - [ ] Under "Actions permissions", select "Allow all actions and reusable workflows"

- [ ] Create Personal Access Token for GHCR:
  - [ ] Go to GitHub Settings → Developer settings → Personal access tokens
  - [ ] Create token with `read:packages` and `write:packages` scopes
  - [ ] Save token for deployment server setup

### Branch Protection

- [ ] Go to Settings → Branches
- [ ] Add rule for `main` branch:
  - [ ] Require pull request reviews before merging
  - [ ] Require status checks to pass:
    - [ ] `test`
    - [ ] `build-and-push`
    - [ ] `security-scan` (for main branch)
  - [ ] Require branches to be up to date before merging
  - [ ] Include administrators in restrictions

- [ ] Add rule for `develop` branch:
  - [ ] Require status checks to pass:
    - [ ] `test`
    - [ ] `build-and-push`

### Environments

- [ ] Create `staging` environment:
  - [ ] Go to Settings → Environments
  - [ ] Click "New environment"
  - [ ] Name: `staging`
  - [ ] (Optional) Require approval before deployment

- [ ] Create `production` environment:
  - [ ] Name: `production`
  - [ ] **Enable:** "Require reviewers" (Select 2+ reviewers)
  - [ ] Set URL: `https://maaps.example.com`

## Phase 3: Staging Server Setup

### Server Preparation

- [ ] SSH into staging server:
  ```bash
  ssh deploy@staging.example.com
  ```

- [ ] Install Docker:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker deploy
  ```

- [ ] Install Docker Compose:
  ```bash
  sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
    -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
  ```

- [ ] Clone repository:
  ```bash
  cd /opt
  sudo git clone https://github.com/your-org/maaps.git
  sudo chown -R deploy:deploy maaps
  cd maaps
  ```

- [ ] Configure environment:
  ```bash
  cp .env.example .env
  nano .env  # Edit with staging values
  ```

- [ ] Set up container registry login:
  ```bash
  docker login ghcr.io
  # Use personal access token created above
  ```

- [ ] Test deployment:
  ```bash
  docker compose pull
  docker compose up -d
  docker compose ps
  curl http://localhost:8080/health
  ```

### Firewall Rules

- [ ] Allow SSH (port 22)
- [ ] Allow HTTP (port 80) - optional for staging
- [ ] Allow HTTPS (port 443) - optional for staging
- [ ] Restrict access to PostgreSQL port 5432 (internal only)
- [ ] Restrict access to Qdrant port 6333 (internal only)

## Phase 4: Production Server Setup

### Server Preparation

- [ ] SSH into production server:
  ```bash
  ssh deploy@prod.example.com
  ```

- [ ] Install Docker:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker deploy
  newgrp docker  # Activate docker group
  ```

- [ ] Install Docker Compose (latest):
  ```bash
  sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
    -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
  docker compose version
  ```

- [ ] Clone repository:
  ```bash
  cd /opt
  sudo git clone https://github.com/your-org/maaps.git
  sudo chown -R deploy:deploy maaps
  cd maaps
  ```

- [ ] Configure environment (use production credentials):
  ```bash
  cp .env.example .env
  nano .env  # Edit with PRODUCTION values!
  ```

- [ ] Set up container registry login:
  ```bash
  docker login ghcr.io
  ```

### SSL/TLS Setup

- [ ] Install Certbot:
  ```bash
  sudo apt-get install certbot python3-certbot-nginx
  ```

- [ ] Generate certificate:
  ```bash
  sudo certbot certonly --standalone -d maaps.example.com
  ```

- [ ] Set up reverse proxy (Nginx recommended):
  ```bash
  sudo apt-get install nginx
  # Configure reverse proxy to localhost:8080
  ```

- [ ] Enable auto-renewal:
  ```bash
  sudo systemctl enable certbot.timer
  sudo systemctl start certbot.timer
  ```

### Firewall Rules

- [ ] Allow SSH (port 22) - restricted to admin IPs only
- [ ] Allow HTTP (port 80) - for Let's Encrypt renewal
- [ ] Allow HTTPS (port 443) - public access
- [ ] Deny PostgreSQL (port 5432)
- [ ] Deny Qdrant (port 6333)
- [ ] Deny Selenium (port 4444)

### Backup Configuration

- [ ] Set up PostgreSQL backups:
  ```bash
  # Add to crontab
  0 2 * * * docker compose exec -T postgres pg_dump -U maaps maaps | \
    gzip > /backups/maaps-$(date +\%Y\%m\%d).sql.gz
  ```

- [ ] Set up volume backups for critical data

- [ ] Test restore procedure monthly

## Phase 5: GitHub Actions Workflow

- [ ] Push to `develop` branch
- [ ] Monitor Actions tab for workflow execution
- [ ] Verify test job passes
- [ ] Verify build job succeeds
- [ ] Verify deploy-staging job completes
- [ ] Confirm staging deployment: `curl https://staging.internal:8080/health`

- [ ] Create Pull Request to `main`
- [ ] Request reviewers
- [ ] Merge after approval
- [ ] Monitor Actions tab for main branch workflow
- [ ] Verify test job passes
- [ ] Verify build job succeeds
- [ ] Verify security-scan job completes
- [ ] Review Trivy scan results in GitHub Security tab
- [ ] Approve production deployment (if required)
- [ ] Monitor deploy-production job
- [ ] Verify production deployment: `curl https://maaps.example.com/health`

## Phase 6: Monitoring & Alerting

### Application Monitoring

- [ ] Set up application metrics collection (optional):
  ```bash
  # e.g., Prometheus, DataDog, New Relic
  ```

- [ ] Configure log aggregation (optional):
  ```bash
  # e.g., CloudWatch, ELK, Datadog
  ```

### Health Checks

- [ ] Test orchestrator health endpoint:
  ```bash
  curl https://maaps.example.com/health
  ```

- [ ] Set up uptime monitoring:
  - [ ] Pingdom, UptimeRobot, or similar service
  - [ ] Configure alerts to Slack

### Alerts Configuration

- [ ] Configure Slack alerts:
  - [ ] GitHub Actions failures
  - [ ] Container crashes
  - [ ] High memory usage
  - [ ] High CPU usage
  - [ ] Disk space low

- [ ] Configure email alerts:
  - [ ] Daily health digest
  - [ ] Critical issues only

## Phase 7: Testing & Validation

### Smoke Tests

- [ ] Test orchestrator API:
  ```bash
  curl https://maaps.example.com/health
  curl https://maaps.example.com/status
  ```

- [ ] Test audio worker:
  ```bash
  curl http://audio-worker.internal:8000/health
  ```

- [ ] Test database:
  ```bash
  docker compose exec postgres psql -U maaps -d maaps -c "SELECT 1;"
  ```

### Load Testing (optional)

- [ ] Install load testing tool (e.g., Apache Bench, k6)
- [ ] Run basic load test:
  ```bash
  ab -n 1000 -c 10 https://maaps.example.com/health
  ```

### Disaster Recovery

- [ ] Test backup restore procedure
- [ ] Verify rollback works:
  ```bash
  ./scripts/deploy.sh production --rollback
  ```

- [ ] Document recovery time objective (RTO)
- [ ] Document recovery point objective (RPO)

## Phase 8: Security Hardening

### Container Security

- [ ] Run as non-root user ✓ (already configured)
- [ ] Enable read-only root filesystem (update docker-compose.yml)
- [ ] Remove unnecessary capabilities (update docker-compose.yml)
- [ ] Scan images for vulnerabilities (already in CI/CD)

### Server Security

- [ ] Install and configure fail2ban:
  ```bash
  sudo apt-get install fail2ban
  sudo systemctl enable fail2ban
  ```

- [ ] Disable password authentication (SSH key only):
  ```bash
  sudo nano /etc/ssh/sshd_config
  # Set: PasswordAuthentication no
  ```

- [ ] Set up firewall (UFW or equivalent):
  ```bash
  sudo ufw default deny incoming
  sudo ufw default allow outgoing
  sudo ufw allow 22/tcp
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  sudo ufw enable
  ```

### Secrets Management

- [ ] Never commit `.env` file with secrets
- [ ] Rotate secrets quarterly
- [ ] Use GitHub Secrets for sensitive data
- [ ] Consider HashiCorp Vault for larger deployments

## Phase 9: Documentation

- [ ] Review `DEPLOYMENT.md`
- [ ] Review `DEPLOYMENT_QUICK_REF.md`
- [ ] Create runbook for on-call engineers
- [ ] Document custom environment variables
- [ ] Document known issues and workarounds
- [ ] Update team wiki/docs

## Phase 10: Team Training

- [ ] Train team on deployment process
- [ ] Review monitoring dashboard
- [ ] Practice incident response procedure
- [ ] Set up on-call rotation
- [ ] Document escalation contacts

---

## Verification Checklist (Before Go-Live)

- [ ] All tests passing on main branch
- [ ] Container images building successfully
- [ ] Staging deployment working
- [ ] Production deployment ready to go
- [ ] SSL certificate installed and valid
- [ ] Monitoring and alerts configured
- [ ] Backups tested and working
- [ ] Team trained on deployment process
- [ ] Incident response procedure documented
- [ ] Rollback procedure tested

## Post-Deployment (First Week)

- [ ] Monitor logs for errors
- [ ] Check resource usage (CPU, memory, disk)
- [ ] Verify database performance
- [ ] Monitor application metrics
- [ ] Gather team feedback
- [ ] Document issues and fixes
- [ ] Plan optimizations

---

**Checklist Version:** 1.0
**Last Updated:** 2024
**Next Review:** After first production deployment
