# GitHub Setup Instructions

Complete these steps to enable the deployment pipeline.

## Step 1: Create SSH Deployment Keys

Run this command on your local machine (not on servers yet):

```bash
# Generate ED25519 SSH key for deployment
ssh-keygen -t ed25519 -f ~/.ssh/maaps_deploy -N ""

# Display the private key (you'll add this to GitHub as DEPLOY_KEY)
cat ~/.ssh/maaps_deploy
```

**Save the output** - you'll need it in Step 3.

## Step 2: Add Public Key to Deployment Servers

**For Staging Server:**

```bash
# Copy public key to staging server
ssh-copy-id -i ~/.ssh/maaps_deploy.pub deploy@staging.example.com

# Verify it works
ssh -i ~/.ssh/maaps_deploy deploy@staging.example.com "echo Connected to staging"
```

**For Production Server:**

```bash
# Copy public key to production server
ssh-copy-id -i ~/.ssh/maaps_deploy.pub deploy@prod.example.com

# Verify it works
ssh -i ~/.ssh/maaps_deploy deploy@prod.example.com "echo Connected to production"
```

## Step 3: Add GitHub Secrets

Go to: **GitHub Repo → Settings → Secrets and variables → Actions**

Click **"New repository secret"** and add these secrets:

### Required Secrets

#### 1. DEPLOY_KEY
**Value:** Output of `cat ~/.ssh/maaps_deploy` from Step 1

**Type:** SSH private key (the entire content)

---

#### 2. DEPLOY_HOST_STAGING
**Value:** Your staging server hostname or IP

**Examples:**
- `staging.maaps.internal`
- `192.168.1.100`
- `staging-server.example.com`

---

#### 3. DEPLOY_USER_STAGING
**Value:** SSH username on staging server (usually `deploy`)

**Default:** `deploy`

---

#### 4. DEPLOY_HOST_PROD
**Value:** Your production server hostname or IP

**Examples:**
- `prod.maaps.example.com`
- `prod-server.internal`

---

#### 5. DEPLOY_USER_PROD
**Value:** SSH username on production server

**Default:** `deploy`

---

#### 6. STAGING_URL
**Value:** Full URL to staging application

**Examples:**
- `http://staging.internal:8080`
- `http://192.168.1.100:8080`

---

#### 7. PROD_URL
**Value:** Full URL to production application

**Examples:**
- `https://maaps.example.com`
- `https://prod.maaps.internal`

---

#### 8. SLACK_WEBHOOK (Optional)

**To get Slack webhook:**
1. Go to https://api.slack.com/messaging/webhooks
2. Click "Create New App"
3. Select "From scratch"
4. Name: `MAAPS Notifications`
5. Choose your workspace
6. Enable "Incoming Webhooks"
7. Click "Add New Webhook to Workspace"
8. Select channel (e.g., #deployments)
9. Copy the webhook URL

**Value:** The full webhook URL (starts with `https://hooks.slack.com/...`)

---

## Step 4: Configure Branch Protection Rules

Go to: **GitHub Repo → Settings → Branches**

### For `main` branch:

1. Click **"Add rule"**
2. **Branch name pattern:** `main`
3. Check: **"Require pull request reviews before merging"**
   - Required number of reviews: 2
4. Check: **"Require status checks to pass before merging"**
   - Require branches to be up to date: ✓
   - Add checks:
     - `test`
     - `build-and-push`
     - `security-scan`
5. Check: **"Include administrators"**
6. Click **"Create"**

### For `develop` branch:

1. Click **"Add rule"**
2. **Branch name pattern:** `develop`
3. Check: **"Require pull request reviews before merging"**
   - Required number of reviews: 1
4. Check: **"Require status checks to pass before merging"**
   - Add checks:
     - `test`
     - `build-and-push`
5. Click **"Create"**

---

## Step 5: Create GitHub Environments

Go to: **GitHub Repo → Settings → Environments**

### Create `staging` environment:

1. Click **"New environment"**
2. Name: `staging`
3. (Optional) Check "Require reviewers" if you want approval
4. Click **"Configure environment"**

### Create `production` environment:

1. Click **"New environment"**
2. Name: `production`
3. Check **"Require reviewers"** (recommended)
   - Add your team members as reviewers
4. Check **"Prevent self-review"** (optional)
5. Set deployment branches to `main` only
6. Click **"Configure environment"**

---

## Step 6: Enable Container Registry

The workflow uses GitHub Container Registry (GHCR) by default.

**No action needed** - GitHub enables GHCR automatically when you push your first image.

However, you can configure it manually:

1. Go to: **GitHub Repo → Settings → Actions → General**
2. Under "Actions permissions": Select "Allow all actions and reusable workflows"
3. Under "GitHub Codespaces": Leave defaults or configure as needed

---

## Step 7: Test the Pipeline

### Test staging deployment:

```bash
# Switch to develop branch
git checkout develop

# Make a small test commit
echo "# Test deployment" >> README.md
git add README.md
git commit -m "test: trigger staging deployment pipeline"
git push origin develop
```

**What happens:**
1. GitHub Actions workflow starts automatically
2. Tests run
3. Images build
4. Push to container registry
5. Deploy to staging automatically
6. Slack notification sent (if configured)

**Monitor at:** https://github.com/your-org/MAAPS_Nexus_V1_V5/actions

---

### Test production deployment:

```bash
# Create PR from develop to main
git checkout main
git pull origin develop

# Or create PR through GitHub UI

# After approval, workflow will:
# 1. Run tests
# 2. Build images
# 3. Security scan
# 4. Wait for approval (if configured)
# 5. Deploy to production
# 6. Send notification
```

---

## Troubleshooting Setup

### "SSH connection failed"

**Check:**
1. SSH key has correct permissions:
   ```bash
   ls -la ~/.ssh/maaps_deploy
   # Should show: -rw------- (600)
   ```

2. Test connection manually:
   ```bash
   ssh -i ~/.ssh/maaps_deploy deploy@staging.example.com "echo test"
   ```

3. Verify public key on server:
   ```bash
   ssh deploy@staging.example.com "cat ~/.ssh/authorized_keys | grep maaps_deploy"
   ```

### "GitHub secret not found"

1. Verify secret name matches exactly (case-sensitive)
2. Go to Settings → Secrets → verify it's listed
3. Re-add the secret if needed

### "Slack notification not received"

1. Check webhook URL is correct and complete
2. Verify Slack channel is in the webhook
3. Check GitHub Actions logs for webhook errors
4. Send a test message:
   ```bash
   curl -X POST -H 'Content-type: application/json' \
     --data '{"text":"Test message"}' \
     YOUR_WEBHOOK_URL
   ```

---

## Next Steps

After completing all steps:

1. ✅ Verify SSH keys work
2. ✅ Verify GitHub secrets are added
3. ✅ Verify branch protection rules are active
4. ✅ Test deploy to staging (commit to develop)
5. ✅ Monitor workflow at GitHub Actions tab
6. ✅ Verify staging deployment succeeded
7. ✅ Create PR to main and test production deployment

---

## Support

Having issues? Check:
- `.github/workflows/ci-cd.yml` - workflow definition
- GitHub Actions "Runs" tab - detailed logs
- Deployment server logs: `docker compose logs`
- SSH connectivity: `ssh -v` for verbose output

---

**Next:** See [DEPLOYMENT.md](./DEPLOYMENT.md) for full documentation
