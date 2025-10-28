#!/bin/bash
# ============================================================================
# Cleanup Unused Kafka Consumer Groups
# ============================================================================

set -e

echo "=========================================="
echo "Kafka Consumer Group Cleanup"
echo "=========================================="
echo ""

# Get list of all consumer groups
GROUPS=$(docker exec kg-kafka kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --list 2>/dev/null)

echo "Found $(echo "$GROUPS" | wc -l) consumer groups"
echo ""

# Arrays to track groups
declare -a EMPTY_GROUPS=()
declare -a STABLE_GROUPS=()
declare -a TEMP_GROUPS=()

# Analyze each group
while IFS= read -r group; do
    if [ -z "$group" ]; then continue; fi

    # Get group state
    STATE=$(docker exec kg-kafka kafka-consumer-groups.sh \
        --bootstrap-server localhost:9092 \
        --group "$group" \
        --describe 2>/dev/null | tail -n +2 | awk '{print $6}' | head -1)

    # Classify groups
    if [[ "$group" == console-consumer-* ]]; then
        TEMP_GROUPS+=("$group")
    elif [[ "$STATE" == "EMPTY" ]]; then
        EMPTY_GROUPS+=("$group")
    else
        STABLE_GROUPS+=("$group")
    fi
done <<< "$GROUPS"

echo "📊 Analysis:"
echo "  - Stable groups (active): ${#STABLE_GROUPS[@]}"
echo "  - Empty groups (inactive): ${#EMPTY_GROUPS[@]}"
echo "  - Temporary console groups: ${#TEMP_GROUPS[@]}"
echo ""

# Show groups to delete
if [ ${#TEMP_GROUPS[@]} -gt 0 ] || [ ${#EMPTY_GROUPS[@]} -gt 0 ]; then
    echo "=========================================="
    echo "Groups Recommended for Deletion"
    echo "=========================================="
    echo ""

    if [ ${#TEMP_GROUPS[@]} -gt 0 ]; then
        echo "🗑️  Temporary console groups (${#TEMP_GROUPS[@]}):"
        printf '   - %s\n' "${TEMP_GROUPS[@]}"
        echo ""
    fi

    if [ ${#EMPTY_GROUPS[@]} -gt 0 ]; then
        echo "🗑️  Empty/inactive groups (${#EMPTY_GROUPS[@]}):"
        printf '   - %s\n' "${EMPTY_GROUPS[@]}"
        echo ""
    fi

    echo "=========================================="
    echo "⚠️  WARNING: This will delete ${#TEMP_GROUPS[@]} console groups and ${#EMPTY_GROUPS[@]} empty groups"
    echo "=========================================="
    echo ""
    read -p "Do you want to proceed? (yes/no): " CONFIRM

    if [ "$CONFIRM" == "yes" ]; then
        echo ""
        echo "Deleting groups..."

        # Delete console groups
        for group in "${TEMP_GROUPS[@]}"; do
            echo "  Deleting: $group"
            docker exec kg-kafka kafka-consumer-groups.sh \
                --bootstrap-server localhost:9092 \
                --delete \
                --group "$group" 2>/dev/null || echo "    Failed to delete $group"
        done

        # Delete empty groups
        for group in "${EMPTY_GROUPS[@]}"; do
            echo "  Deleting: $group"
            docker exec kg-kafka kafka-consumer-groups.sh \
                --bootstrap-server localhost:9092 \
                --delete \
                --group "$group" 2>/dev/null || echo "    Failed to delete $group"
        done

        echo ""
        echo "✅ Cleanup complete!"
    else
        echo "Cancelled."
    fi
else
    echo "✅ No groups need cleanup!"
fi

echo ""
echo "=========================================="
echo "Remaining Stable Groups"
echo "=========================================="
echo ""
if [ ${#STABLE_GROUPS[@]} -gt 0 ]; then
    printf '✅ %s\n' "${STABLE_GROUPS[@]}"
else
    echo "None"
fi
echo ""
