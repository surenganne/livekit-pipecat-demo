#!/bin/bash

# LiveKit + Pipecat Demo - Robust Agent Startup Script
# This script starts the agent with automatic crash recovery

set -e

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$PROJECT_DIR/agent"
CLIENT_DIR="$PROJECT_DIR/client"
ENV_FILE="$PROJECT_DIR/.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%H:%M:%S')] ERROR:${NC} $1"
}

# Function to check if a process is running
is_running() {
    local name=$1
    pgrep -f "$name" >/dev/null 2>&1
}

# Function to stop a process gracefully
stop_process() {
    local name=$1
    local timeout=${2:-10}
    
    if is_running "$name"; then
        log "Stopping $name..."
        pkill -f "$name" || true
        
        # Wait for graceful shutdown
        local count=0
        while is_running "$name" && [ $count -lt $timeout ]; do
            sleep 1
            ((count++))
        done
        
        # Force kill if still running
        if is_running "$name"; then
            warn "Force killing $name..."
            pkill -9 -f "$name" || true
        fi
        
        log "$name stopped"
    fi
}

# Function to check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check if .env file exists
    if [ ! -f "$ENV_FILE" ]; then
        error ".env file not found at $ENV_FILE"
        error "Please copy .env.template to .env and configure your API keys"
        exit 1
    fi
    
    # Check if required Python packages are installed
    cd "$AGENT_DIR"
    if ! python3 -c "import pipecat, livekit" 2>/dev/null; then
        error "Required Python packages not installed"
        error "Please run: pip install -r requirements.txt"
        exit 1
    fi
    
    # Check if psutil is available for supervisor
    if ! python3 -c "import psutil" 2>/dev/null; then
        warn "psutil not installed. Installing..."
        pip install psutil
    fi
    
    log "Prerequisites check passed ✅"
}

# Function to start Docker services (LiveKit + Redis)
start_docker_services() {
    log "Checking Docker services (LiveKit + Redis)..."
    
    cd "$PROJECT_DIR"
    
    # Check if both services are running
    livekit_running=$(docker-compose ps livekit | grep -q "Up" && echo "true" || echo "false")
    redis_running=$(docker-compose ps redis | grep -q "Up" && echo "true" || echo "false")
    
    if [ "$livekit_running" = "true" ] && [ "$redis_running" = "true" ]; then
        log "Docker services already running ✅"
        log "  - LiveKit: Running ✅"
        log "  - Redis: Running ✅"
    else
        log "Starting Docker services (LiveKit + Redis)..."
        
        # Start all services defined in docker-compose.yml
        docker-compose up -d
        
        # Wait for services to be ready with health checks
        log "Waiting for services to be ready..."
        sleep 5
        
        # Wait for LiveKit to be responsive with health checks
        log "Checking LiveKit health..."
        for i in {1..30}; do
            if curl -s -f http://localhost:7880 >/dev/null 2>&1; then
                log "LiveKit is responding to health checks ✅"
                break
            else
                if [ $i -eq 30 ]; then
                    error "LiveKit failed to become responsive after 30 attempts"
                    docker-compose logs livekit --tail 20
                    exit 1
                fi
                sleep 1
            fi
        done
        
        # Additional wait for full initialization
        log "Allowing extra time for full LiveKit initialization..."
        sleep 3
        
        # Verify both services are running
        livekit_running=$(docker-compose ps livekit | grep -q "Up" && echo "true" || echo "false")
        redis_running=$(docker-compose ps redis | grep -q "Up" && echo "true" || echo "false")
        
        if [ "$livekit_running" = "true" ] && [ "$redis_running" = "true" ]; then
            log "Docker services started successfully ✅"
            log "  - LiveKit: Running on ports 7880-7881 ✅"
            log "  - Redis: Running on port 6379 ✅"
        else
            error "Failed to start Docker services:"
            if [ "$livekit_running" = "false" ]; then
                error "  - LiveKit: Failed ❌"
            fi
            if [ "$redis_running" = "false" ]; then
                error "  - Redis: Failed ❌"
            fi
            
            log "Docker service status:"
            docker-compose ps
            
            log "Docker logs:"
            docker-compose logs --tail 10
            
            exit 1
        fi
    fi
}

# Function to start HTTP server for client
start_http_server() {
    log "Checking HTTP server..."
    
    if lsof -i :8000 >/dev/null 2>&1; then
        log "HTTP server is already running ✅"
    else
        log "Starting HTTP server on port 8000..."
        cd "$CLIENT_DIR"
        python3 -m http.server 8000 > /tmp/http_server.log 2>&1 &
        sleep 2
        
        if is_running "python.*http.server.*8000"; then
            log "HTTP server started ✅"
            log "Client available at: http://localhost:8000"
        else
            error "Failed to start HTTP server"
            exit 1
        fi
    fi
}

# Function to start supervised agent
start_supervised_agent() {
    local mode=${1:-normal}
    
    log "Starting supervised Pipecat agent..."
    
    # Stop any existing agents
    stop_process "spawn_agent.py"
    stop_process "supervisor.py"
    
    cd "$AGENT_DIR"
    
    # Start supervisor in background
    python3 supervisor.py > /tmp/agent_supervisor.log 2>&1 &
    
    sleep 3
    
    if is_running "supervisor.py"; then
        log "Agent supervisor started ✅"
        log "Agent logs: tail -f /tmp/pipecat_agent.log"
        log "Supervisor logs: tail -f /tmp/agent_supervisor.log"
    else
        error "Failed to start agent supervisor"
        exit 1
    fi
}

# Function to show status
show_status() {
    echo
    log "=== SERVICE STATUS ==="
    
    cd "$PROJECT_DIR"
    
    # LiveKit status
    if docker-compose ps livekit | grep -q "Up"; then
        echo -e "LiveKit Server: ${GREEN}Running ✅${NC}"
    else
        echo -e "LiveKit Server: ${RED}Stopped ❌${NC}"
    fi
    
    # Redis status
    if docker-compose ps redis | grep -q "Up"; then
        echo -e "Redis Server:   ${GREEN}Running ✅${NC}"
    else
        echo -e "Redis Server:   ${RED}Stopped ❌${NC}"
    fi
    
    # HTTP server status
    if lsof -i :8000 >/dev/null 2>&1; then
        echo -e "HTTP Server:    ${GREEN}Running ✅${NC} (http://localhost:8000)"
    else
        echo -e "HTTP Server:    ${RED}Stopped ❌${NC}"
    fi
    
    # Agent supervisor status
    if is_running "supervisor.py"; then
        echo -e "Agent Super:    ${GREEN}Running ✅${NC}"
    else
        echo -e "Agent Super:    ${RED}Stopped ❌${NC}"
    fi
    
    # Agent status
    if is_running "spawn_agent.py"; then
        echo -e "Intelligent Agent: ${GREEN}Running ✅${NC}"
    else
        echo -e "Intelligent Agent: ${RED}Stopped ❌${NC}"
    fi
    
    echo
}

# Function to perform comprehensive cleanup to prevent duplicate identity issues
cleanup_everything() {
    log "🧹 Performing comprehensive cleanup to prevent duplicate identity issues..."
    
    # 1. Stop all Python processes (agents, supervisors, HTTP server)
    log "Stopping Python processes..."
    stop_process "supervisor.py" 15
    stop_process "spawn_agent.py" 10
    stop_process "python.*http.server.*8000" 5
    
    # 2. Force kill any remaining agent processes
    log "Force killing any remaining agent processes..."
    pkill -9 -f "spawn_agent.py" 2>/dev/null || true
    pkill -9 -f "supervisor.py" 2>/dev/null || true
    
    # 3. Stop and remove Docker containers with volumes to clear state
    cd "$PROJECT_DIR"
    log "Stopping and removing Docker containers with volumes..."
    docker-compose down --volumes 2>/dev/null || true
    
    # 4. Clean up any orphaned Docker containers
    log "Cleaning up orphaned containers..."
    docker container prune -f 2>/dev/null || true
    
    # 5. Clear log files to start fresh
    log "Clearing log files..."
    rm -f /tmp/pipecat_agent.log /tmp/agent_supervisor.log /tmp/http_server.log
    
    # 6. Wait for cleanup to complete
    sleep 2
    
    log "✅ Comprehensive cleanup completed - ready for fresh start"
}

# Function to stop all services
stop_all() {
    cleanup_everything
}

# Function to show logs
show_logs() {
    local service=$1
    case $service in
        "agent")
            tail -f /tmp/pipecat_agent.log
            ;;
        "supervisor")
            tail -f /tmp/agent_supervisor.log
            ;;
        "http")
            tail -f /tmp/http_server.log
            ;;
        "livekit")
            cd "$PROJECT_DIR"
            docker-compose logs -f livekit
            ;;
        "redis")
            cd "$PROJECT_DIR"
            docker-compose logs -f redis
            ;;
        *)
            echo "Available logs: agent, supervisor, http, livekit, redis"
            ;;
    esac
}

# Main script logic
case "${1:-start}" in
    "start")
        log "🚀 Starting LiveKit + Pipecat Demo with Auto-Restart"
        
        # Always do cleanup before starting to prevent duplicate identity issues
        cleanup_everything
        
        check_prerequisites
        start_docker_services
        
        # Additional stabilization time for LiveKit/Redis integration
        log "Allowing additional time for service stabilization..."
        sleep 2
        
        start_http_server
        start_supervised_agent
        show_status
        log "🎉 All services started successfully!"
        log "💡 Use './run.sh status' to check service status"
        log "💡 Use './run.sh logs agent' to view agent logs"
        ;;
    
    "stop")
        stop_all
        ;;
    
    "restart")
        stop_all
        sleep 2
        $0 start
        ;;
    
    "status")
        show_status
        ;;
    
    "logs")
        show_logs $2
        ;;
    
    "agent-only")
        log "Starting only the supervised agent..."
        check_prerequisites
        start_supervised_agent
        ;;
    
    "clean")
        log "🧹 Manual cleanup requested"
        cleanup_everything
        log "🎉 Cleanup completed - ready for fresh start"
        ;;
    
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|agent-only|clean}"
        echo
        echo "Commands:"
        echo "  start      - Start all services (LiveKit, HTTP server, intelligent agent)"
        echo "  stop       - Stop all services"
        echo "  restart    - Restart all services"
        echo "  status     - Show service status"
        echo "  logs <svc> - Show logs (agent, supervisor, http, livekit)"
        echo "  agent-only - Start only the supervised agent"
        echo "  clean      - Comprehensive cleanup to prevent duplicate identity issues"
        echo
        exit 1
        ;;
esac
