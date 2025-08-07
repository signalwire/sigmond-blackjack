#!/bin/bash
# Blackjack Dealer Bot Manager - Start/Stop Blackjack Dealer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="sigmond_blackjack.pid"
LOG_FILE="sigmond_blackjack.log"
DEALER_SCRIPT="$SCRIPT_DIR/sigmond_blackjack.py"
DEFAULT_PORT=3010  # Different port from tarot (3009)

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if Dealer is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        else
            # PID file exists but process is dead
            rm -f "$PID_FILE"
            return 1
        fi
    fi
    return 1
}

# Start Blackjack Dealer
start_dealer() {
    if is_running; then
        echo -e "${YELLOW}Blackjack Dealer is already running with PID: $(cat "$PID_FILE")${NC}"
        return 1
    fi
    
    echo -e "${GREEN}Starting Blackjack Dealer ...${NC}"
    
    # Check if dealer script exists
    if [ ! -f "$DEALER_SCRIPT" ]; then
        echo -e "${RED}Error: $DEALER_SCRIPT not found!${NC}"
        return 1
    fi
    
    # Start Dealer in background and redirect output to log file
    nohup python3 "$DEALER_SCRIPT" --port $DEFAULT_PORT > "$LOG_FILE" 2>&1 &
    PID=$!
    
    # Save PID to file
    echo $PID > "$PID_FILE"
    
    # Wait a moment to check if it started successfully
    sleep 2
    
    if is_running; then
        echo -e "${GREEN}✅ Blackjack Dealer started successfully!${NC}"
        echo -e "   🎰 PID: $PID"
        echo -e "   📝 Log: $LOG_FILE"
        echo -e "   🌐 URL: http://localhost:$DEFAULT_PORT/blackjack"
        
        # Try to extract auth credentials from log
        if [ -f "$LOG_FILE" ]; then
            AUTH=$(grep "Basic Auth:" "$LOG_FILE" | tail -1)
            if [ ! -z "$AUTH" ]; then
                echo -e "   🔑 $AUTH"
            fi
        fi
        echo -e ""
        echo -e "   ${YELLOW}Starting chips: 1000${NC}"
        echo -e "   ${YELLOW}Minimum bet: 10 chips${NC}"
        echo -e "   ${YELLOW}Rules: Dealer hits on 16, stands on 17${NC}"
    else
        echo -e "${RED}❌ Failed to start Blackjack Dealer${NC}"
        echo -e "   Check $LOG_FILE for errors"
        return 1
    fi
}

# Stop Blackjack Dealer
stop_dealer() {
    if ! is_running; then
        echo -e "${YELLOW}Blackjack Dealer is not running${NC}"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    echo -e "${GREEN}Stopping Blackjack Dealer (PID: $PID)...${NC}"
    
    # Send SIGTERM for graceful shutdown
    kill -TERM "$PID" 2>/dev/null
    
    # Wait up to 5 seconds for process to stop
    for i in {1..5}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # If still running, force kill
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}Dealer didn't stop gracefully, forcing shutdown...${NC}"
        kill -9 "$PID" 2>/dev/null
    fi
    
    # Clean up PID file
    rm -f "$PID_FILE"
    
    echo -e "${GREEN}✅ Blackjack Dealer has been stopped${NC}"
}

# Check Dealer's status
status_dealer() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo -e "${GREEN}● Blackjack Dealer is running${NC}"
        echo -e "   🎰 PID: $PID"
        echo -e "   🌐 URL: http://localhost:$DEFAULT_PORT/blackjack"
        
        # Show process info
        ps -p "$PID" -o pid,vsz,rss,comm
        
        # Show last few log lines
        if [ -f "$LOG_FILE" ]; then
            echo -e "\n${YELLOW}Recent log entries:${NC}"
            tail -5 "$LOG_FILE"
        fi
    else
        echo -e "${RED}● Blackjack Dealer is not running${NC}"
    fi
}

# Show logs
show_logs() {
    if [ -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}Blackjack Dealer logs (press Ctrl+C to exit):${NC}"
        tail -f "$LOG_FILE"
    else
        echo -e "${RED}No log file found${NC}"
    fi
}

# Main script logic
case "$1" in
    start)
        start_dealer
        ;;
    stop)
        stop_dealer
        ;;
    restart)
        stop_dealer
        sleep 1
        start_dealer
        ;;
    status)
        status_dealer
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "🎰 Blackjack Dealer Bot Manager"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start    - Start Blackjack Dealer in the background"
        echo "  stop     - Stop Blackjack Dealer gracefully"
        echo "  restart  - Restart Blackjack Dealer"
        echo "  status   - Check if Dealer is running"
        echo "  logs     - Follow Dealer's logs"
        echo ""
        echo "Example:"
        echo "  $0 start   # Start Blackjack Dealer"
        echo "  $0 status  # Check status"
        echo "  $0 stop    # Stop Dealer"
        echo ""
        echo "Default port: $DEFAULT_PORT (different from tarot's 3009)"
        ;;
esac
