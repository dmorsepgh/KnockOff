#!/bin/bash
# Safe start for Smirnoff - prevents system crashes

echo "🔍 Pre-flight checks..."

# 1. Check disk space (need at least 15GB free)
AVAILABLE=$(df -g / | tail -1 | awk '{print $4}')
if [ "$AVAILABLE" -lt 15 ]; then
    echo "❌ ABORT: Only ${AVAILABLE}GB free on internal drive"
    echo "Need at least 15GB to avoid crashes"
    exit 1
fi
echo "✅ Disk space OK: ${AVAILABLE}GB free"

# 2. Check if already running (prevent duplicate processes)
if pgrep -f "auto-process-queue" > /dev/null; then
    echo "❌ ABORT: Smirnoff already running!"
    echo "Kill it first: pkill -f auto-process-queue"
    exit 1
fi
echo "✅ No conflicts detected"

# 3. Check WDblack is mounted
if [ ! -d "/Volumes/WDblack1tb - Data" ]; then
    echo "❌ ABORT: WDblack not mounted!"
    echo "Temp files need external drive"
    exit 1
fi
echo "✅ WDblack mounted"

# 4. Check NAS is mounted
if [ ! -d "/Volumes/homes" ]; then
    echo "⚠️  WARNING: NAS not mounted (videos won't backup)"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ NAS mounted"
fi

# 5. Set resource limits (prevent memory overflow)
ulimit -v 8388608  # 8GB max virtual memory
ulimit -m 6291456  # 6GB max resident memory

echo ""
echo "🚀 All checks passed - starting Smirnoff..."
echo "Monitor: tail -f /tmp/smirnoff-queue.log"
echo "Stop: pkill -f auto-process-queue"
echo ""

cd /Users/mac/KnockOff
nohup ./auto-process-queue.sh > /tmp/smirnoff-queue.log 2>&1 &
PID=$!

echo "✅ Smirnoff started (PID: $PID)"
echo ""
echo "Safety measures active:"
echo "  - Max memory: 6GB"
echo "  - Disk space monitored"
echo "  - Single process only"
echo ""
