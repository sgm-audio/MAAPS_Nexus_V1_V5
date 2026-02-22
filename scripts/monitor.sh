#!/bin/bash

# MAAPS Deployment Status Monitor
# Usage: ./scripts/monitor.sh [staging|production]

set -euo pipefail

ENVIRONMENT=${1:-}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

usage() {
    cat << EOF
Usage: $0 [staging|production]

Monitor deployment status and service health

Examples:
  $0 staging
  $0 production

EOF
    exit 1
}

if [[ -z "$ENVIRONMENT" || "$ENVIRONMENT" == "-h" || "$ENVIRONMENT" == "--help" ]]; then
    usage
fi

if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
    echo "Environment must be 'staging' or 'production'"
    exit 1
fi

# Load config
source "$PROJECT_ROOT/.env" || {
    echo "Error: .env file not found"
    exit 1
}

case "$ENVIRONMENT" in
    staging)
        DEPLOY_HOST="${DEPLOY_HOST_STAGING:-}"
        DEPLOY_USER="${DEPLOY_USER_STAGING:-}"
        SERVICE_URL="${STAGING_URL:-}"
        ;;
    production)
        DEPLOY_HOST="${DEPLOY_HOST_PROD:-}"
        DEPLOY_USER="${DEPLOY_USER_PROD:-}"
        SERVICE_URL="${PROD_URL:-}"
        ;;
esac

if [[ -z "$DEPLOY_HOST" ]]; then
    echo "Error: Deployment host not configured for $ENVIRONMENT"
    exit 1
fi

print_header() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
}

print_status() {
    local status=$1
    local message=$2
    
    if [[ "$status" == "✓" ]]; then
        echo -e "${GREEN}[$status]${NC} $message"
    else
        echo -e "${RED}[$status]${NC} $message"
    fi
}

check_ssh() {
    print_header "SSH Connectivity"
    
    if ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
        "${DEPLOY_USER}@${DEPLOY_HOST}" exit 2>/dev/null; then
        print_status "✓" "SSH connection successful"
        return 0
    else
        print_status "✗" "SSH connection failed"
        return 1
    fi
}

check_containers() {
    print_header "Container Status"
    
    local output=$(ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << 'EOF'
cd /opt/maaps
docker compose ps --format "{{.Names}} {{.Status}}"
EOF
    )
    
    echo "$output" | while read -r line; do
        if [[ -z "$line" ]]; then
            continue
        fi
        
        container=$(echo "$line" | awk '{print $1}')
        status=$(echo "$line" | awk '{$1=""; print substr($0,2)}')
        
        if [[ "$status" == "Up"* ]]; then
            print_status "✓" "$container: $status"
        else
            print_status "✗" "$container: $status"
        fi
    done
}

check_health() {
    print_header "Service Health"
    
    if curl -sf "$SERVICE_URL/health" > /dev/null 2>&1; then
        print_status "✓" "Orchestrator health: OK"
    else
        print_status "✗" "Orchestrator health: FAILED"
    fi
    
    # Remote audio worker check
    local audio_status=$(ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << 'EOF'
curl -sf http://localhost:8000/health > /dev/null 2>&1 && echo "OK" || echo "FAILED"
EOF
    )
    
    if [[ "$audio_status" == "OK" ]]; then
        print_status "✓" "Audio Worker health: OK"
    else
        print_status "✗" "Audio Worker health: FAILED"
    fi
}

check_disk_space() {
    print_header "Disk Space"
    
    ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << 'EOF'
df -h /opt/maaps | tail -n 1 | awk '{print "Mounted at: " $6 "\nUsed: " $3 " / " $2 " (" $5 ")"}'
EOF
}

check_database() {
    print_header "Database Connectivity"
    
    local db_status=$(ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << 'EOF'
cd /opt/maaps
docker compose exec -T postgres pg_isready -U maaps -d maaps > /dev/null 2>&1 && echo "OK" || echo "FAILED"
EOF
    )
    
    if [[ "$db_status" == "OK" ]]; then
        print_status "✓" "PostgreSQL: Connected"
    else
        print_status "✗" "PostgreSQL: Connection failed"
    fi
}

check_recent_logs() {
    print_header "Recent Errors (Last 20 lines)"
    
    ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << 'EOF'
cd /opt/maaps
echo "=== Orchestrator Errors ==="
docker compose logs --tail=20 orchestrator | grep -i "error\|exception" || echo "(no errors)"
echo ""
echo "=== Audio Worker Errors ==="
docker compose logs --tail=20 audio_worker | grep -i "error\|exception" || echo "(no errors)"
EOF
}

git_status() {
    print_header "Git Status"
    
    local branch=$(ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << 'EOF'
cd /opt/maaps
git rev-parse --abbrev-ref HEAD
EOF
    )
    
    local commit=$(ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << 'EOF'
cd /opt/maaps
git rev-parse --short HEAD
EOF
    )
    
    local dirty=$(ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << 'EOF'
cd /opt/maaps
[[ -z $(git status -s) ]] && echo "clean" || echo "dirty"
EOF
    )
    
    echo "Branch: $branch"
    echo "Commit: $commit"
    echo "Working dir: $dirty"
}

# Main
echo -e "${BLUE}MAAPS Deployment Monitor${NC}"
echo "Environment: $ENVIRONMENT"
echo "Host: ${DEPLOY_USER}@${DEPLOY_HOST}"
echo "Service URL: $SERVICE_URL"

check_ssh || exit 1
check_containers
check_health
check_database
check_disk_space
check_recent_logs
git_status

echo ""
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo "Monitoring complete"
echo -e "${BLUE}════════════════════════════════════════${NC}"
