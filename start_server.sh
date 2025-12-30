#!/bin/bash
# Kill any existing server on port 8000
echo "Checking for existing processes on port 8000..."
PIDS=$(netstat -ano | grep ":8000.*LISTENING" | awk '{print $5}' | sort -u)
if [ -n "$PIDS" ]; then
    echo "Found processes: $PIDS"
    for pid in $PIDS; do
        echo "Killing PID $pid"
        taskkill //F //PID $pid 2>/dev/null || true
    done
    sleep 2
fi

# Verify port is free
if netstat -ano | grep ":8000.*LISTENING" > /dev/null; then
    echo "ERROR: Port 8000 still occupied!"
    exit 1
fi

echo "Starting server..."
python -m playgram
