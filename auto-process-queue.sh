#!/bin/bash
# Auto-process video queue and move to NAS

QUEUE=(
    "count-to-30-test.md"  # Timing test - 30 second count
    "superbowl-food.md"    # Super Bowl party food trends
    "90-day-path.md"       # The simple path to millionaire in 90 days
    "day-4-infrastructure.md"  # Day 4 - Building the execution system
    # "odl-architecture-explainer.md"  # Day 5 - WAITING FOR SCALEWAY
    "daily-output-explainer.md"  # Zero-input AI - what we built today
)

OUTPUT_DIR="/Users/mac/KnockOff/.tmp/avatar/output"
NAS_DIR="/Volumes/homes/videos/smirnoff-output"
COMPARISON_DIR="/Volumes/WDblack1tb - Data/video-comparisons"

cd /Users/mac/KnockOff
source .venv/bin/activate

for script in "${QUEUE[@]}"; do
    echo "=================================="
    echo "Processing: $script"
    echo "Started: $(date)"
    echo "=================================="

    # Run the generation
    python tools/generate_avatar_video.py \
        --script "scripts/$script" \
        --avatar doug \
        --voice doug

    # Wait a moment for file to be written
    sleep 5

    # Find the most recent MP4 in output
    LATEST=$(ls -t "$OUTPUT_DIR"/*.mp4 2>/dev/null | head -1)

    if [ -f "$LATEST" ]; then
        # Generate descriptive name from script name
        BASENAME=$(basename "$script" .md)
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        NEW_NAME="${BASENAME}-${TIMESTAMP}.mp4"
        COMPARISON_NAME="KO-${BASENAME}.mp4"

        # Save to NAS
        echo "Saving to NAS: $NEW_NAME"
        cp "$LATEST" "$NAS_DIR/$NEW_NAME"

        # Save to comparison folder
        echo "Saving to comparison: $COMPARISON_NAME"
        mkdir -p "$COMPARISON_DIR/$BASENAME"
        cp "$LATEST" "$COMPARISON_DIR/$BASENAME/$COMPARISON_NAME"

        # Verify copies succeeded
        if [ -f "$NAS_DIR/$NEW_NAME" ] && [ -f "$COMPARISON_DIR/$BASENAME/$COMPARISON_NAME" ]; then
            echo "✅ Saved to NAS: $NEW_NAME"
            echo "✅ Saved for comparison: $COMPARISON_DIR/$BASENAME/$COMPARISON_NAME"
            rm "$LATEST"  # Remove from temp
        else
            echo "❌ Failed to copy files"
        fi
    else
        echo "⚠️  No output file found for $script"
    fi

    echo "Completed: $(date)"
    echo ""
done

echo "=================================="
echo "ALL VIDEOS PROCESSED"
echo "NAS backup: $NAS_DIR"
echo "Comparisons: $COMPARISON_DIR"
echo "=================================="
burnout-memoirs-explainer.md
cheftech-marketing.md
