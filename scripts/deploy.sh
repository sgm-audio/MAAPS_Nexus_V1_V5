#!/bin/bash

# MAAPS Deployment Helper Script
# Usage: ./scripts/deploy.sh [staging|production] [--force] [--rollback]

set -euo pipefail

ENVIRONMENT=${1:-}
FORCE=${2:-}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

usage() {
    cat << EOF
Usage: $0 [staging|production] [OPTIONS]

Options:
  --force       Skip confirmation prompts
  --rollback    Rollback to previous version
  -h, --help    Show this help message

Examples:
  $0 staging                    # Deploy to staging (with confirmation)
  $0 production --force         # Deploy to production (force)
  $0 staging --rollback         # Rollback staging deployment

EOF
    exit 1
}

validate_env() {
    if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
        log_error "Environment must be 'staging' or 'production'"
        usage
    fi

    if [[ "$ENVIRONMENT" == "production" && "$FORCE" != "--force" ]]; then
        log_warn "Production deployment requires --force flag"
        exit 1
    fi

    # Load environment configuration
    source "$PROJECT_ROOT/.env" || {
        log_error ".env file not found"
        exit 1
    }
}

get_deployment_config() {
    case "$ENVIRONMENT" in
        staging)
            DEPLOY_HOST="${DEPLOY_HOST_STAGING:-}"
            DEPLOY_USER="${DEPLOY_USER_STAGING:-}"
            DEPLOY_KEY="${DEPLOY_KEY_STAGING:-}"
            SERVICE_URL="${STAGING_URL:-}"
            ;;
        production)
            DEPLOY_HOST="${DEPLOY_HOST_PROD:-}"
            DEPLOY_USER="${DEPLOY_USER_PROD:-}"
            DEPLOY_KEY="${DEPLOY_KEY_PROD:-}"
            SERVICE_URL="${PROD_URL:-}"
            ;;
    esac

    if [[ -z "$DEPLOY_HOST" || -z "$DEPLOY_USER" ]]; then
        log_error "Missing deployment configuration for $ENVIRONMENT"
        log_error "Set DEPLOY_HOST_${ENVIRONMENT^^} and DEPLOY_USER_${ENVIRONMENT^^}"
        exit 1
    fi
}

confirm_deployment() {
    if [[ "$FORCE" == "--force" ]]; then
        return 0
    fi

    read -p "Deploy to $ENVIRONMENT? (yes/no): " -r
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        log_warn "Deployment cancelled"
        exit 0
    fi
}

check_git_status() {
    cd "$PROJECT_ROOT"
    
    if [[ -n $(git status -s) ]]; then
        log_warn "Working directory has uncommitted changes"
        git status -s
        
        if [[ "$ENVIRONMENT" == "production" ]]; then
            log_error "Cannot deploy production with uncommitted changes"
            exit 1
        fi
        
        if [[ "$FORCE" != "--force" ]]; then
            read -p "Continue anyway? (yes/no): " -r
            if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
                exit 0
            fi
        fi
    fi
}

build_locally() {
    log_info "Building images locally..."
    cd "$PROJECT_ROOT"
    
    docker compose build orchestrator audio_worker || {
        log_error "Local build failed"
        exit 1
    }
    
    log_info "Local build successful"
}

run_tests() {
    log_info "Running tests..."
    cd "$PROJECT_ROOT"
    
    python -m pytest tests/ -v || {
        log_error "Tests failed"
        if [[ "$ENVIRONMENT" == "production" ]]; then
            exit 1
        fi
    }
    
    log_info "Tests passed"
}

deploy() {
    if [[ "$2" == "--rollback" ]]; then
        rollback_deployment
        return
    fi

    log_info "Deploying to $ENVIRONMENT ($DEPLOY_HOST)..."

    local deploy_script=$(cat << 'DEPLOY_SCRIPT'
set -euo pipefail
cd /opt/maaps

echo "[*] Pulling latest code..."
git pull origin $(git rev-parse --abbrev-ref HEAD)

echo "[*] Pulling latest images..."
docker compose pull

echo "[*] Stopping containers..."
docker compose down

echo "[*] Starting new containers..."
docker compose up -d

echo "[*] Verifying configuration..."
sleep 5
docker compose exec -T orchestrator python -c "from core import Config; print('Config loaded successfully')" || exit 1

echo "[*] Checking service health..."
for i in {1..30}; do
    if curl -f http://localhost:8080/health 2>/dev/null; then
        echo "[✓] Service is healthy"
        exit 0
    fi
    echo "[$i/30] Waiting for service to be ready..."
    sleep 2
done

echo "[✗] Health check failed"
exit 1
DEPLOY_SCRIPT
    )

    ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
        "${DEPLOY_USER}@${DEPLOY_HOST}" <<< "$deploy_script" || {
        log_error "Deployment failed"
        return 1
    }
}

rollback_deployment() {
    log_warn "Rolling back $ENVIRONMENT..."

    local rollback_script=$(cat << 'ROLLBACK_SCRIPT'
set -euo pipefail
cd /opt/maaps

echo "[*] Reverting to previous version..."
git reset --hard HEAD~1

echo "[*] Pulling previous images..."
docker compose pull

echo "[*] Restarting services..."
docker compose down
docker compose up -d

echo "[*] Checking health..."
for i in {1..30}; do
    if curl -f http://localhost:8080/health 2>/dev/null; then
        echo "[✓] Rollback successful"
        exit 0
    fi
    sleep 2
done

echo "[✗] Rollback health check failed"
exit 1
ROLLBACK_SCRIPT
    )

    ssh -o ConnectTimeout=10 "${DEPLOY_USER}@${DEPLOY_HOST}" <<< "$rollback_script" || {
        log_error "Rollback failed"
        return 1
    }
}

health_check() {
    log_info "Running health checks..."
    
    for i in {1..10}; do
        if curl -f "$SERVICE_URL/health" 2>/dev/null; then
            log_info "Health check passed"
            return 0
        fi
        echo "Attempt $i/10..."
        sleep 2
    done

    log_error "Health check failed"
    return 1
}

show_logs() {
    log_info "Fetching deployment logs..."
    
    ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << 'LOG_SCRIPT'
cd /opt/maaps
echo "=== Last 50 lines of orchestrator logs ==="
docker compose logs --tail=50 orchestrator
echo ""
echo "=== Last 50 lines of audio_worker logs ==="
docker compose logs --tail=50 audio_worker
LOG_SCRIPT
}

# Main
if [[ "$ENVIRONMENT" == "-h" || "$ENVIRONMENT" == "--help" || -z "$ENVIRONMENT" ]]; then
    usage
fi

validate_env
get_deployment_config

check_git_status

if [[ "$ENVIRONMENT" == "staging" ]]; then
    log_info "Building and testing locally..."
    build_locally
    run_tests
fi

confirm_deployment

deploy "$ENVIRONMENT" "$FORCE"

if health_check; then
    log_info "Deployment to $ENVIRONMENT completed successfully!"
else
    log_error "Deployment completed but health check failed"
    show_logs
    exit 1
fi
