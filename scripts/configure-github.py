#!/usr/bin/env python3

"""
MAAPS GitHub Configuration Tool
Automates GitHub repository configuration for deployment pipeline.

Usage:
    python3 configure-github.py --token YOUR_GITHUB_TOKEN --owner your-username --repo MAAPS_Nexus_V1_V5

Requirements:
    pip install PyGithub
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    from github import Github, GithubException
except ImportError:
    print("Error: PyGithub not installed")
    print("Install with: pip install PyGithub")
    sys.exit(1)


class GitHubConfigurator:
    """Configure GitHub repository for MAAPS deployment pipeline"""

    def __init__(self, token: str, owner: str, repo: str):
        self.g = Github(token)
        self.owner = owner
        self.repo_name = repo
        self.repo = self._get_repo()

    def _get_repo(self):
        """Get repository object"""
        try:
            return self.g.get_user(self.owner).get_repo(self.repo_name)
        except GithubException as e:
            print(f"Error: Cannot access repository {self.owner}/{self.repo_name}")
            print(f"Details: {e}")
            sys.exit(1)

    def print_section(self, title: str):
        """Print section header"""
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")

    def print_success(self, message: str):
        """Print success message"""
        print(f"✓ {message}")

    def print_error(self, message: str):
        """Print error message"""
        print(f"✗ {message}")

    def print_warning(self, message: str):
        """Print warning message"""
        print(f"! {message}")

    def check_secrets(self) -> List[str]:
        """Check which secrets are already configured"""
        self.print_section("Checking Configured Secrets")

        required_secrets = [
            "DEPLOY_KEY",
            "DEPLOY_HOST_STAGING",
            "DEPLOY_USER_STAGING",
            "DEPLOY_HOST_PROD",
            "DEPLOY_USER_PROD",
            "STAGING_URL",
            "PROD_URL",
        ]

        try:
            # We can't read secrets directly, but we can inform the user
            print("Note: GitHub doesn't allow reading secret values")
            print("You must configure these secrets manually or via GitHub CLI\n")
            for secret in required_secrets:
                print(f"  □ {secret}")
            return required_secrets
        except Exception as e:
            self.print_error(f"Error checking secrets: {e}")
            return []

    def create_environments(self):
        """Create staging and production environments"""
        self.print_section("Creating Environments")

        environments = {
            "staging": {
                "description": "Staging environment (develop branch)",
                "reviewers": [],
                "auto_trigger_on": ["develop"],
            },
            "production": {
                "description": "Production environment (main branch)",
                "reviewers": [],
                "auto_trigger_on": ["main"],
            },
        }

        try:
            for env_name, env_config in environments.items():
                print(f"\nNote: Create '{env_name}' environment manually:")
                print(f"  1. Go to: Settings → Environments")
                print(f"  2. Click 'New environment'")
                print(f"  3. Name: {env_name}")
                if env_name == "production":
                    print(f"  4. Check 'Require reviewers'")
                    print(f"  5. Add team members as reviewers")
                print(f"\n  Description: {env_config['description']}")
        except Exception as e:
            self.print_error(f"Error creating environments: {e}")

    def configure_branch_protection(self):
        """Configure branch protection rules"""
        self.print_section("Configuring Branch Protection")

        rules = {
            "main": {
                "required_status_checks": ["test", "build-and-push", "security-scan"],
                "required_pull_request_reviews": 2,
                "description": "Main production branch",
            },
            "develop": {
                "required_status_checks": ["test", "build-and-push"],
                "required_pull_request_reviews": 1,
                "description": "Development branch",
            },
        }

        for branch, config in rules.items():
            try:
                protection = self.repo.get_branch(branch).protection

                if protection:
                    self.print_warning(f"Branch '{branch}' already has protection rules")
                    print(f"  Status checks: {config['required_status_checks']}")
                else:
                    print(f"\n📋 To protect branch '{branch}':")
                    print(f"  1. Go to: Settings → Branches")
                    print(f"  2. Click 'Add rule'")
                    print(f"  3. Branch name pattern: {branch}")
                    print(f"  4. ✓ Require pull request reviews ({config['required_pull_request_reviews']})")
                    print(f"  5. ✓ Require status checks:")
                    for check in config["required_status_checks"]:
                        print(f"     - {check}")
                    print(f"  6. ✓ Include administrators")
                    print(f"  7. Click 'Create'")

            except GithubException as e:
                if "branch not found" in str(e):
                    self.print_warning(f"Branch '{branch}' not found (will be created automatically)")
                else:
                    self.print_error(f"Error checking branch '{branch}': {e}")

    def print_secrets_template(self):
        """Print GitHub Secrets template"""
        self.print_section("GitHub Secrets Template")

        template = """
Add these secrets to GitHub:
Settings → Secrets and variables → Actions → New repository secret

DEPLOY_KEY
──────────
(Output of: cat ~/.ssh/maaps_deploy)
[Paste entire private key here]

DEPLOY_HOST_STAGING
───────────────────
staging.example.com
(or IP address like 192.168.1.100)

DEPLOY_USER_STAGING
───────────────────
deploy

DEPLOY_HOST_PROD
────────────────
prod.example.com
(or IP address)

DEPLOY_USER_PROD
────────────────
deploy

STAGING_URL
───────────
http://staging.internal:8080

PROD_URL
────────
https://maaps.example.com

SLACK_WEBHOOK (Optional)
────────────────────────
https://hooks.slack.com/services/YOUR/WEBHOOK/URL
(Leave empty to skip Slack notifications)
"""
        print(template)

    def print_workflow_status(self):
        """Check workflow status"""
        self.print_section("Workflow Status")

        try:
            workflows = list(self.repo.get_workflows())
            if workflows:
                for workflow in workflows:
                    print(f"\n  Workflow: {workflow.name}")
                    print(f"    Path: {workflow.path}")
                    print(f"    State: {workflow.state}")
                    print(f"    Badge: [![{workflow.name}]({workflow.badge_url})]({workflow.html_url})")
            else:
                self.print_warning("No workflows found")
        except Exception as e:
            self.print_error(f"Error checking workflows: {e}")

    def generate_setup_guide(self):
        """Generate setup guide document"""
        self.print_section("Generating Setup Guide")

        guide = f"""# MAAPS Deployment Pipeline Setup

Repository: {self.owner}/{self.repo_name}
Branch: main, develop

## Quick Setup

### 1. Generate SSH Key

```bash
ssh-keygen -t ed25519 -f ~/.ssh/maaps_deploy -N ""
cat ~/.ssh/maaps_deploy
```

### 2. Add to Deployment Servers

```bash
ssh-copy-id -i ~/.ssh/maaps_deploy.pub deploy@staging.example.com
ssh-copy-id -i ~/.ssh/maaps_deploy.pub deploy@prod.example.com
```

### 3. Add GitHub Secrets

Go to: https://github.com/{self.owner}/{self.repo_name}/settings/secrets/actions

Required secrets:
- DEPLOY_KEY (SSH private key)
- DEPLOY_HOST_STAGING
- DEPLOY_USER_STAGING
- DEPLOY_HOST_PROD
- DEPLOY_USER_PROD
- STAGING_URL
- PROD_URL
- SLACK_WEBHOOK (optional)

### 4. Set Branch Protection

Go to: https://github.com/{self.owner}/{self.repo_name}/settings/branches

Main branch requires:
- 2 PR reviews
- Status checks: test, build-and-push, security-scan

Develop branch requires:
- 1 PR review
- Status checks: test, build-and-push

### 5. Test Pipeline

```bash
git checkout develop
echo "test" >> README.md
git commit -am "test: pipeline trigger"
git push origin develop
```

Monitor at: https://github.com/{self.owner}/{self.repo_name}/actions

## Documentation

- DEPLOYMENT.md - Full documentation
- DEPLOYMENT_QUICK_REF.md - Quick reference
- GITHUB_SETUP_GUIDE.md - Detailed setup steps
"""

        output_file = Path("SETUP_GUIDE_GENERATED.md")
        output_file.write_text(guide)
        self.print_success(f"Setup guide generated: {output_file}")

    def run(self):
        """Run full configuration"""
        print(f"\n{'='*60}")
        print(f"  MAAPS GitHub Configuration Tool")
        print(f"{'='*60}")
        print(f"Repository: {self.owner}/{self.repo_name}")

        # Check repository
        try:
            print(f"Repository URL: {self.repo.html_url}")
            print(f"Description: {self.repo.description or '(no description)'}")
        except Exception as e:
            self.print_error(f"Cannot access repository: {e}")
            sys.exit(1)

        # Run configuration steps
        self.print_secrets_template()
        self.configure_branch_protection()
        self.create_environments()
        self.print_workflow_status()
        self.generate_setup_guide()

        self.print_section("Next Steps")
        print("""
1. ✓ Review and note the GitHub Secrets above
2. Go to: Settings → Secrets and variables → Actions
3. Add each secret listed above
4. Go to: Settings → Branches
5. Add branch protection rules (see above)
6. Go to: Settings → Environments
7. Create 'staging' and 'production' environments
8. Test the pipeline with a commit to 'develop' branch

For detailed instructions, see: GITHUB_SETUP_GUIDE.md
        """)


def main():
    parser = argparse.ArgumentParser(
        description="Configure GitHub repository for MAAPS deployment pipeline"
    )
    parser.add_argument(
        "--token",
        required=True,
        help="GitHub personal access token (scope: repo, workflows)",
    )
    parser.add_argument("--owner", required=True, help="Repository owner (username)")
    parser.add_argument("--repo", required=True, help="Repository name")

    args = parser.parse_args()

    configurator = GitHubConfigurator(args.token, args.owner, args.repo)
    configurator.run()


if __name__ == "__main__":
    main()
