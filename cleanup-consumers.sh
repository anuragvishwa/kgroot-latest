#!/bin/bash
# cleanup-consumers.sh - Clean up unused Kafka consumer groups
# Usage: ./cleanup-consumers.sh

KAFKA_HOST="mini-server"
KAFKA_CONTAINER="kg-kafka"
BOOTSTRAP_SERVER="localhost:9092"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔍 Fetching all consumer groups...${NC}"
GROUPS=$(ssh $KAFKA_HOST "docker exec $KAFKA_CONTAINER kafka-consumer-groups.sh \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --list" 2>/dev/null)

if [ -z "$GROUPS" ]; then
  echo -e "${RED}❌ Failed to fetch consumer groups${NC}"
  exit 1
fi

echo -e "${BLUE}📋 Current consumer groups:${NC}"
echo "$GROUPS"
echo ""

# Active groups to keep (edit this list based on your active deployments)
KEEP_GROUPS=(
  "kg-builder-af-10"
  # Add more active consumer groups here
)

echo -e "${YELLOW}🗑️  Consumer groups to delete:${NC}"
TO_DELETE=()
while IFS= read -r group; do
  # Skip empty lines
  [ -z "$group" ] && continue

  # Check if group should be kept
  KEEP=0
  for keep_group in "${KEEP_GROUPS[@]}"; do
    if [ "$group" == "$keep_group" ]; then
      KEEP=1
      echo -e "  ${GREEN}✓ Keeping:${NC} $group"
      break
    fi
  done

  if [ $KEEP -eq 0 ]; then
    echo -e "  ${RED}✗ Deleting:${NC} $group"
    TO_DELETE+=("$group")
  fi
done <<< "$GROUPS"

if [ ${#TO_DELETE[@]} -eq 0 ]; then
  echo ""
  echo -e "${GREEN}✅ No consumer groups to delete!${NC}"
  echo -e "${GREEN}All consumer groups are in the keep list.${NC}"
  exit 0
fi

echo ""
echo -e "${YELLOW}⚠️  This will delete ${#TO_DELETE[@]} consumer groups!${NC}"
read -p "Continue? (y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo -e "${BLUE}Cleanup cancelled.${NC}"
  exit 0
fi

echo ""
echo -e "${BLUE}🔨 Deleting consumer groups...${NC}"

SUCCESS=0
FAILED=0

for group in "${TO_DELETE[@]}"; do
  echo -n "Deleting $group... "
  RESULT=$(ssh $KAFKA_HOST "docker exec $KAFKA_CONTAINER kafka-consumer-groups.sh \
    --bootstrap-server $BOOTSTRAP_SERVER \
    --delete \
    --group \"$group\"" 2>&1)

  if echo "$RESULT" | grep -q "successful"; then
    echo -e "${GREEN}✅${NC}"
    ((SUCCESS++))
  else
    echo -e "${RED}❌${NC}"
    echo "$RESULT"
    ((FAILED++))
  fi
done

echo ""
echo -e "${BLUE}📊 Summary:${NC}"
echo -e "  ${GREEN}✅ Successful: $SUCCESS${NC}"
echo -e "  ${RED}❌ Failed: $FAILED${NC}"

echo ""
echo -e "${BLUE}📋 Remaining consumer groups:${NC}"
ssh $KAFKA_HOST "docker exec $KAFKA_CONTAINER kafka-consumer-groups.sh \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --list"

echo ""
echo -e "${GREEN}🎉 Cleanup complete!${NC}"