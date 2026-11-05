# MAAPS Deployment Pipeline - Complete Setup Guide

This guide walks you through setting up the entire deployment pipeline from scratch.

**Total setup time:** 30-45 minutes  
**Complexity:** Medium

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Phase 1: Local Machine Setup](#phase-1-local-machine-setup)
3. [Phase 2: GitHub Configuration](#phase-2-github-configuration)
4. [Phase 3: Staging Server Setup](#phase-3-staging-server-setup)
5. [Phase 4: Production Server Setup](#phase-4-production-server-setup)
6. [Phase 5: Test Deployment](#phase-5-test-deployment)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

You need:

- ✅ Local machine (Mac, Linux, or Windows with WSL)
- ✅ SSH client (`ssh` command available)
- ✅ Git installed
- ✅ GitHub account with repository access
- ✅ 2 servers (staging and production) with:
  - Ubuntu 20.04+ or Debian 11+
  - Root or sudo access
  - Internet access
  - ~20GB disk space minimum
- ✅ (Optional) Slack workspace for notifications

---

## Phase 1: Local Machine Setup

### 1.1 Generate SSH Deployment Key

This key allows GitHub Actions to deploy to your servers.

```bash
# Generate SSH key (use default location)
ssh-keygen -t ed25519 -f ~/.ssh/maaps_deploy -N ""

# Verify it was created
ls -la ~/.ssh/maaps_deploy*
# Should show two files:
#   maaps_deploy (private key)
#   maaps_deploy.pub (public key)

# Display the private key (you'll need this later)
cat ~/.ssh/maaps_deploy
```

**Save the output** - you'll add it to GitHub Secrets in Phase 2.

### 1.2 Gather Required Information

Create a notepad with these values (you'll need them throughout setup):

```
Staging Server:
  Hostname/IP: ___________________
  SSH Port: ___________________
  
Production Server:
  Hostname/IP: ___________________
  SSH Port: ___________________

GitHub:
  Repository: scottmill306/MAAPS_Nexus_V1_V5
  Owner: scottmill306
  
Slack (optional):
  Webhook URL: ___________________
```

---

## Phase 2: GitHub Configuration

### 2.1 Create GitHub Personal Access Token

1. Go to: https://github.com/settings/tokens
2. Click **"Generate new token (classic)"**
3. Set **Expiration:** 90 days
4. Check scopes:
   - ✓ `repo` (full control of private repositories)
   - ✓ `workflow` (update GitHub Action workflows)
5. Click **"Generate token"**
6. **Copy the token** - you'll use it only once

### 2.2 Add GitHub Secrets

Go to: https://github.com/scottmill306/MAAPS_Nexus_V1_V5/settings/secrets/actions

Click **"New repository secret"** for each of these:

#### 1. `DEPLOY_KEY`

**Value:** Output from `cat ~/.ssh/maaps_deploy` (the entire private key)

**Paste the full key**, including:
```
-----BEGIN OPENSSH PRIVATE KEY-----
[middle section]
-----END OPENSSH PRIVATE KEY-----
```

#### 2. `DEPLOY_HOST_STAGING`

**Value:** Your staging server hostname or IP

Example: `staging.example.com` or `192.168.1.100`

#### 3. `DEPLOY_USER_STAGING`

**Value:** `deploy`

(This user will be created on the staging server in Phase 3)

#### 4. `DEPLOY_HOST_PROD`

**Value:** Your production server hostname or IP

Example: `prod.example.com`

#### 5. `DEPLOY_USER_PROD`

**Value:** `deploy`

#### 6. `STAGING_URL`

**Value:** Full URL to staging application

Example: `http://staging.internal:8080`

#### 7. `PROD_URL`

**Value:** Full URL to production application

Example: `https://maaps.example.com`

#### 8. `SLACK_WEBHOOK` (Optional)

**To create Slack webhook:**
1. Go to https://api.slack.com/messaging/webhooks
2. Click **"Create New App"**
3. Select **"From scratch"**
4. Name: `MAAPS Notifications`
5. Choose your workspace
6. Click **"Create App"**
7. Click **"Incoming Webhooks"** in left menu
8. Turn ON "Activate Incoming Webhooks"
9. Click **"Add New Webhook to Workspace"**
10. Select channel (e.g., #deployments)
11. Copy the webhook URL

**Value:** The full webhook URL (starts with `https://hooks.slack.com/...`)

### 2.3 Configure Branch Protection

Go to: https://github.com/scottmill306/MAAPS_Nexus_V1_V5/settings/branches

#### Protect `main` branch:

1. Click **"Add rule"**
2. **Branch name pattern:** `main`
3. Check: **"Require pull request reviews before merging"**
   - Set to: **2** reviewers
4. Check: **"Require status checks to pass before merging"**
   - Require branches to be up to date before merging: ✓
   - Add required checks:
     - [ ] `test`
     - [ ] `build-and-push`
     - [ ] `security-scan`
5. Check: **"Include administrators"**
6. Click **"Create"**

#### Protect `develop` branch:

1. Click **"Add rule"**
2. **Branch name pattern:** `develop`
3. Check: **"Require pull request reviews before merging"**
   - Set to: **1** reviewer
4. Check: **"Require status checks to pass before merging"**
   - Add required checks:
     - [ ] `test`
     - [ ] `build-and-push`
5. Click **"Create"**

### 2.4 Create Environments

Go to: https://github.com/scottmill306/MAAPS_Nexus_V1_V5/settings/environments

#### Create `staging` environment:

1. Click **"New environment"**
2. Name: `staging`
3. (Optional) Check "Require reviewers" if you want approval for staging deploys
4. Click **"Configure environment"**

#### Create `production` environment:

1. Click **"New environment"**
2. Name: `production`
3. Check **"Require reviewers"** (highly recommended)
   - Add 2-3 team members who can approve production deploys
4. Check **"Prevent self-review"** (optional but recommended)
5. Click **"Configure environment"**

---

## Phase 3: Staging Server Setup

### 3.1 Connect to Staging Server

```bash
# SSH into staging server (replace with your IP/hostname)
ssh root@staging.example.com

# Or if SSH is on non-standard port
ssh -p 2222 root@staging.example.com
```

### 3.2 Run Server Setup Script

```bash
# Download setup script
curl -O https://raw.githubusercontent.com/scottmill306/MAAPS_Nexus_V1_V5/main/scripts/setup-server.sh

# Run the script
bash setup-server.sh staging

# The script will:
# ✓ Update system
# ✓ Install Docker and Docker Compose
# ✓ Create 'deploy' user
# ✓ Clone MAAPS repository
# ✓ Set up automated backups
# ✓ Configure firewall (ufw)
```

The script takes 5-10 minutes. When it finishes, note the **"Next Steps"** section.

### 3.3 Add SSH Public Key

On your **local machine**:

```bash
# Copy public key to staging server
ssh-copy-id -i ~/.ssh/maaps_deploy.pub deploy@staging.example.com

# Verify it works
ssh -i ~/.ssh/maaps_deploy deploy@staging.example.com "echo 'SSH working!'"
```

### 3.4 Configure Environment Variables

SSH back into staging:

```bash
ssh deploy@staging.example.com

# Edit environment file
nano /opt/maaps/.env
```

**Replace with your values:**

```bash
POSTGRES_USER=maaps
POSTGRES_PASSWORD=your-secure-password-here
QDRANT_API_KEY=your-qdrant-key-here

# Optional APIs
HEARTMULA_API_KEY=
ELEVENLABS_API_KEY=

# Timezone
TZ=UTC
```

Save: `Ctrl+X`, then `Y`, then `Enter`

### 3.5 Login to Container Registry

Still SSH'd into staging:

```bash
docker login ghcr.io

# Username: your-github-username
# Password: [personal access token from Phase 2.1]
```

### 3.6 Test Deployment Locally

Still on staging:

```bash
cd /opt/maaps

# Pull images
docker compose pull

# Start services
docker compose up -d

# Check status
docker compose ps

# Test health
curl http://localhost:8080/health

# View logs if there are issues
docker compose logs orchestrator
```

If everything works, continue to Phase 4. If there are errors, check [Troubleshooting](#troubleshooting).

### 3.7 Configure Firewall (Optional but Recommended)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 8080/tcp
sudo ufw enable

# Verify
sudo ufw status
```

---

## Phase 4: Production Server Setup

**Repeat Phase 3 steps for production server**, with these differences:

```bash
# 1. SSH into production
ssh root@prod.example.com

# 2. Run setup script for production
bash setup-server.sh production

# 3. Add SSH key
ssh-copy-id -i ~/.ssh/maaps_deploy.pub deploy@prod.example.com

# 4. Configure environment with production values
ssh deploy@prod.example.com
nano /opt/maaps/.env

# 5. Login to container registry
docker login ghcr.io

# 6. Test deployment
cd /opt/maaps
docker compose pull
docker compose up -d
docker compose ps
curl http://localhost:8080/health

# 7. Configure firewall (production)
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp              # SSH
sudo ufw allow 80/tcp              # HTTP (Let's Encrypt)
sudo ufw allow 443/tcp             # HTTPS
sudo ufw enable
```

### 4.1 Optional: SSL/TLS Certificate

For production HTTPS:

```bash
sudo apt-get install certbot python3-certbot-nginx

sudo certbot certonly --standalone -d your-domain.com

# Auto-renewal
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

Then configure a reverse proxy (Nginx):

```bash
sudo apt-get install nginx

# Configure /etc/nginx/sites-available/maaps with:
# - Listen on 443 (SSL)
# - Proxy to localhost:8080
# - Use certbot certificate
```

---

## Phase 5: Test Deployment

### 5.1 Test Staging Deployment

```bash
# On your local machine
git checkout develop

# Make a test change
echo "# Testing deployment pipeline" >> README.md

# Commit and push
git add README.md
git commit -m "test: trigger staging deployment"
git push origin develop
```

**Monitor workflow:**
1. Go to: https://github.com/scottmill306/MAAPS_Nexus_V1_V5/actions
2. Watch the workflow run
3. Should see jobs:
   - ✓ `test`
   - ✓ `build-and-push`
   - ✓ `deploy-staging`

**Verify staging deployment:**

```bash
# Test from your local machine
curl http://staging.example.com:8080/health

# Or SSH into staging
ssh deploy@staging.example.com
docker compose ps
docker compose logs orchestrator | tail -20
```

### 5.2 Test Production Deployment

```bash
# On your local machine
git checkout main
git pull origin develop

# Or create PR from develop to main through GitHub UI
# Requires 2 approvals (configured in branch protection)
```

**Monitor workflow:**
1. Workflow runs: `test` → `build-and-push` → `security-scan`
2. Waits for approval (if configured)
3. Then: `deploy-production`

**Verify production deployment:**

```bash
curl https://maaps.example.com/health

# Or SSH into production
ssh deploy@prod.example.com
docker compose ps
curl http://localhost:8080/health
```

---

## Troubleshooting

### SSH Connection Refused

**Problem:** Can't SSH to deployment server

**Solution:**
```bash
# Test SSH key permissions
ls -la ~/.ssh/maaps_deploy
# Should show: -rw------- (600)

chmod 600 ~/.ssh/maaps_deploy

# Test connection with verbose output
ssh -vvv -i ~/.ssh/maaps_deploy deploy@staging.example.com
```

### "Permission denied (publickey)"

**Problem:** SSH key not accepted

**Solution:**
```bash
# On server, check authorized_keys
ssh deploy@staging.example.com "cat ~/.ssh/authorized_keys"

# Should contain your public key
# If not, re-run:
ssh-copy-id -i ~/.ssh/maaps_deploy.pub deploy@staging.example.com
```

### Docker Compose Pull Fails

**Problem:** `image not found` or rate limit errors

**Solution:**
```bash
# On deployment server
docker login ghcr.io
# Enter username and personal access token

# Retry pull
docker compose pull
```

### Containers Exit Immediately

**Problem:** `docker compose ps` shows containers exiting

**Solution:**
```bash
# Check logs
docker compose logs orchestrator

# Common issues:
# - Missing environment variables (.env)
# - Database not accessible
# - Port already in use

# Fix and restart
docker compose down
docker compose up -d
```

### GitHub Actions Workflow Fails

**Problem:** Workflow shows red X

**Solution:**
1. Click workflow run name
2. Click failed job
3. Expand step logs
4. Look for error message
5. Common issues:
   - SSH key format wrong
   - Secret names don't match
   - Status check names don't match

### "Health check failed"

**Problem:** Deployment succeeds but health check fails

**Solution:**
```bash
# SSH to server
ssh deploy@staging.example.com

# Check if service is running
curl http://localhost:8080/health

# Check logs
docker compose logs orchestrator | grep -i error

# Restart
docker compose restart orchestrator

# Wait 30 seconds
sleep 30
curl http://localhost:8080/health
```

---

## Next Steps After Setup

1. ✅ Test deployment to staging (commit to `develop`)
2. ✅ Test deployment to production (PR to `main`)
3. ✅ Set up monitoring/alerts
4. ✅ Configure log aggregation (optional)
5. ✅ Create incident response runbook
6. ✅ Train team on deployment process

---

## Reference Documents

- **DEPLOYMENT.md** - Full deployment documentation
- **DEPLOYMENT_QUICK_REF.md** - Quick commands reference
- **GITHUB_SETUP_GUIDE.md** - GitHub configuration details
- **DEPLOYMENT_SETUP_CHECKLIST.md** - Setup checklist

---

## Support

For issues:

1. Check **DEPLOYMENT_QUICK_REF.md** for quick answers
2. Review **DEPLOYMENT.md** troubleshooting section
3. Check GitHub Actions logs for workflow errors
4. SSH to servers and check container logs

---

**Estimated Total Time:** 30-45 minutes  
**Difficulty:** Medium  
**Support:** See documentation files above

**You're all set! 🚀**

After completing this guide, your deployment pipeline is live and ready to deploy code automatically on every push.
