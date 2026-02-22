#!/bin/bash

# MAAPS Deployment Server Setup Script
# Run this on a fresh Ubuntu 20.04+ or Debian 11+ server
# Usage: bash setup-server.sh [staging|production]

set -euo pipefail

ENVIRONMENT=${1:-}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}! $1${NC}"
}

usage() {
    cat << EOF
Usage: $0 [staging|production]

Setup a deployment server for MAAPS.

Requirements:
  - Ubuntu 20.04+ or Debian 11+
  - Root or sudo access
  - Internet access

Example:
  $0 staging
  $0 production

EOF
    exit 1
}

check_environment() {
    if [[ -z "$ENVIRONMENT" || ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
        print_error "Environment must be 'staging' or 'production'"
        usage
    fi

    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root or with sudo"
        exit 1
    fi
}

update_system() {
    print_header "Updating System"
    
    apt-get update -qq
    apt-get upgrade -y -qq
    apt-get install -y -qq curl wget git openssh-server openssh-client apt-transport-https ca-certificates gnupg lsb-release
    
    print_success "System updated"
}

install_docker() {
    print_header "Installing Docker"
    
    if command -v docker &> /dev/null; then
        print_warning "Docker already installed: $(docker --version)"
        return
    fi
    
    # Add Docker GPG key
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$(lsb_release -is | tr '[:upper:]' '[:lower:]')/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    # Add Docker repository
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(lsb_release -is | tr '[:upper:]' '[:lower:]') $(lsb_release -cs) stable" | \
        tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Start Docker
    systemctl enable docker
    systemctl start docker
    
    print_success "Docker installed and started"
}

install_docker_compose() {
    print_header "Installing Docker Compose"
    
    if command -v docker-compose &> /dev/null; then
        print_warning "Docker Compose already installed: $(docker-compose --version)"
        return
    fi
    
    # Install as standalone
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
    curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    
    print_success "Docker Compose installed: $(docker-compose --version)"
}

install_additional_tools() {
    print_header "Installing Additional Tools"
    
    apt-get install -y -qq htop iotop iftop netcat tmux vim-tiny jq
    
    print_success "Additional tools installed"
}

create_deploy_user() {
    print_header "Creating Deploy User"
    
    if id "deploy" &>/dev/null; then
        print_warning "Deploy user already exists"
        return
    fi
    
    useradd -m -s /bin/bash deploy || true
    usermod -aG docker deploy
    
    # Create .ssh directory
    mkdir -p /home/deploy/.ssh
    chmod 700 /home/deploy/.ssh
    chown -R deploy:deploy /home/deploy/.ssh
    
    print_success "Deploy user created"
    print_warning "Important: Add SSH public key to /home/deploy/.ssh/authorized_keys"
    echo "Run on your local machine:"
    echo "  ssh-copy-id -i ~/.ssh/maaps_deploy.pub deploy@$(hostname)"
}

setup_repository() {
    print_header "Setting Up Repository"
    
    if [[ -d /opt/maaps ]]; then
        print_warning "Repository already exists at /opt/maaps"
        return
    fi
    
    mkdir -p /opt
    cd /opt
    
    git clone https://github.com/scottmill306/MAAPS_Nexus_V1_V5.git maaps
    
    chown -R deploy:deploy /opt/maaps
    
    print_success "Repository cloned to /opt/maaps"
}

setup_environment() {
    print_header "Setting Up Environment"
    
    if [[ -f /opt/maaps/.env ]]; then
        print_warning ".env already exists"
        return
    fi
    
    cd /opt/maaps
    cp .env.example .env
    
    chown deploy:deploy .env
    chmod 600 .env
    
    print_warning "⚠️  IMPORTANT: Edit /opt/maaps/.env with your settings"
    echo "Run:"
    echo "  sudo nano /opt/maaps/.env"
    echo ""
    echo "Or with your values:"
    echo "  sudo tee /opt/maaps/.env > /dev/null << EOF"
    echo "  POSTGRES_USER=maaps"
    echo "  POSTGRES_PASSWORD=your-secure-password"
    echo "  QDRANT_API_KEY=your-qdrant-key"
    echo "  TZ=UTC"
    echo "  EOF"
}

setup_docker_login() {
    print_header "Setting Up Docker Registry Login"
    
    print_warning "You need to login to GitHub Container Registry (GHCR)"
    echo ""
    echo "Steps:"
    echo "1. Go to: https://github.com/settings/tokens"
    echo "2. Generate new token with 'read:packages' and 'write:packages' scopes"
    echo "3. Copy the token"
    echo "4. Run:"
    echo "   sudo -u deploy docker login ghcr.io"
    echo "5. Username: your-github-username"
    echo "6. Password: paste-your-token"
    echo ""
    read -p "Press Enter when docker login is complete..."
}

setup_cron_backups() {
    print_header "Setting Up Automated Backups"
    
    mkdir -p /backups
    chown deploy:deploy /backups
    
    # Create backup script
    cat > /usr/local/bin/maaps-backup.sh << 'BACKUP_SCRIPT'
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
TIMESTAMP=$(date +%Y-%m-%d)

# PostgreSQL backup
docker compose -f /opt/maaps/docker-compose.yml exec -T postgres \
    pg_dump -U maaps maaps | gzip > "$BACKUP_DIR/postgres_$TIMESTAMP.sql.gz"

# Cleanup old backups (keep 7 days)
find "$BACKUP_DIR" -name "postgres_*.sql.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_DIR/postgres_$TIMESTAMP.sql.gz"
BACKUP_SCRIPT

    chmod +x /usr/local/bin/maaps-backup.sh
    
    # Add crontab entry
    if ! sudo -u deploy crontab -l 2>/dev/null | grep -q "maaps-backup"; then
        echo "0 2 * * * /usr/local/bin/maaps-backup.sh >> /var/log/maaps-backup.log 2>&1" | \
            sudo -u deploy crontab -
    fi
    
    print_success "Automated backups configured (2:00 AM daily)"
}

setup_firewall() {
    print_header "Configuring Firewall (ufw)"
    
    if ! command -v ufw &> /dev/null; then
        apt-get install -y -qq ufw
    fi
    
    if ufw status 2>/dev/null | grep -q "inactive"; then
        print_warning "Firewall not active yet"
        echo ""
        echo "After setup completes, run:"
        
        case "$ENVIRONMENT" in
            staging)
                echo "  sudo ufw default deny incoming"
                echo "  sudo ufw default allow outgoing"
                echo "  sudo ufw allow 22/tcp"
                echo "  sudo ufw allow 80/tcp"
                echo "  sudo ufw allow 8080/tcp"
                echo "  sudo ufw enable"
                ;;
            production)
                echo "  sudo ufw default deny incoming"
                echo "  sudo ufw default allow outgoing"
                echo "  sudo ufw allow 22/tcp"
                echo "  sudo ufw allow 80/tcp"
                echo "  sudo ufw allow 443/tcp"
                echo "  sudo ufw enable"
                ;;
        esac
    else
        print_success "Firewall is active"
    fi
}

setup_monitoring() {
    print_header "Setting Up Monitoring"
    
    cat > /usr/local/bin/maaps-health.sh << 'HEALTH_SCRIPT'
#!/bin/bash
set -euo pipefail

echo "=== MAAPS Health Check ==="
echo ""
echo "[Containers]"
cd /opt/maaps
docker compose ps
echo ""
echo "[Services]"
curl -s http://localhost:8080/health && echo "✓ Orchestrator OK" || echo "✗ Orchestrator FAILED"
curl -s http://localhost:8000/health && echo "✓ Audio Worker OK" || echo "✗ Audio Worker FAILED"
echo ""
echo "[Disk Space]"
df -h /opt/maaps
HEALTH_SCRIPT

    chmod +x /usr/local/bin/maaps-health.sh
    
    print_success "Health check script installed"
    echo "Run anytime with: /usr/local/bin/maaps-health.sh"
}

verify_installation() {
    print_header "Verifying Installation"
    
    local all_ok=true
    
    if command -v docker &> /dev/null; then
        print_success "Docker: $(docker --version)"
    else
        print_error "Docker not found"
        all_ok=false
    fi
    
    if command -v docker-compose &> /dev/null; then
        print_success "Docker Compose: $(docker-compose --version)"
    else
        print_error "Docker Compose not found"
        all_ok=false
    fi
    
    if id "deploy" &>/dev/null; then
        print_success "Deploy user exists"
    else
        print_error "Deploy user not found"
        all_ok=false
    fi
    
    if [[ -d /opt/maaps ]]; then
        print_success "Repository: /opt/maaps"
    else
        print_error "Repository not found"
        all_ok=false
    fi
    
    if $all_ok; then
        return 0
    else
        return 1
    fi
}

print_next_steps() {
    print_header "Next Steps"
    
    echo "1. ✅ System and Docker installed"
    echo ""
    echo "2. 🔑 Add SSH public key:"
    echo "   ssh-copy-id -i ~/.ssh/maaps_deploy.pub deploy@$(hostname)"
    echo ""
    echo "3. 📝 Configure environment:"
    echo "   sudo nano /opt/maaps/.env"
    echo ""
    echo "4. 🐳 Login to Docker registry:"
    echo "   sudo -u deploy docker login ghcr.io"
    echo ""
    echo "5. 🚀 Test deployment:"
    echo "   cd /opt/maaps"
    echo "   sudo -u deploy docker compose pull"
    echo "   sudo -u deploy docker compose up -d"
    echo "   /usr/local/bin/maaps-health.sh"
    echo ""
    echo "6. 🛡️  Enable firewall (after testing):"
    echo "   sudo ufw enable"
    echo ""
    
    case "$ENVIRONMENT" in
        production)
            echo "7. 🔐 Configure SSL/TLS (production only):"
            echo "   sudo apt-get install certbot python3-certbot-nginx"
            echo "   sudo certbot certonly --standalone -d your-domain.com"
            echo ""
            ;;
    esac
    
    echo "Server setup complete! 🎉"
}

# Main
check_environment
echo -e "${BLUE}MAAPS Deployment Server Setup${NC}"
echo "Environment: $ENVIRONMENT"
echo "Hostname: $(hostname)"
echo ""

update_system
install_docker
install_docker_compose
install_additional_tools
create_deploy_user
setup_repository
setup_environment
setup_docker_login
setup_cron_backups
setup_firewall
setup_monitoring

if verify_installation; then
    print_next_steps
    exit 0
else
    print_error "Some components failed to install"
    print_next_steps
    exit 1
fi
