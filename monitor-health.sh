#!/bin/bash
# Monitor Smirnoff health and prevent crashes

while true; do
    # Check disk space
    AVAILABLE=$(df -g / | tail -1 | awk '{print $4}')
    if [ "$AVAILABLE" -lt 10 ]; then
        echo "🚨 CRITICAL: Only ${AVAILABLE}GB free!"
        echo "Stopping Smirnoff to prevent crash..."
        pkill -f "auto-process-queue"
        ~/Documents/scripts/text-me.sh "🚨 Smirnoff stopped - disk almost full (${AVAILABLE}GB)"
        break
    fi

    # Check if process died unexpectedly
    if ! pgrep -f "auto-process-queue" > /dev/null; then
        echo "⚠️  Smirnoff stopped unexpectedly"
        ~/Documents/scripts/text-me.sh "⚠️ Smirnoff crashed or stopped"
        break
    fi

    # Check memory usage
    MEM_PERCENT=$(ps aux | grep "wav2lip\|generate_avatar" | grep -v grep | awk '{sum+=$4} END {print int(sum)}')
    if [ "$MEM_PERCENT" -gt 80 ]; then
        echo "⚠️  High memory usage: ${MEM_PERCENT}%"
    fi

    # Status update every 5 minutes
    echo "[$(date +%H:%M)] OK - ${AVAILABLE}GB free, ${MEM_PERCENT}% memory"

    sleep 300  # Check every 5 minutes
done
