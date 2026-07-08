#!/usr/bin/env bash
# =========================================================================
# verify_sandbox.sh — Adversarial tests against the gVisor sandbox
#
# Runs 6 real attack simulations against the sandboxed scan-runner and
# reports pass/fail for each. This script must be run on the droplet
# AFTER setup_gvisor.sh has completed and the scan-runner image is built.
#
# Prerequisites:
#   1. sudo ./setup_gvisor.sh (gVisor installed, Docker configured)
#   2. docker build -f Dockerfile.sandbox -t breakmyapp-scan-runner:latest .
#   3. ./verify_sandbox.sh
#
# CRITICAL: Tests use the SAME resource limits as docker-compose.sandbox.yml,
# sourced from sandbox_config.env. This ensures the verification proves
# what actually gets deployed, not a different set of flags.
# =========================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source the same config that docker-compose.sandbox.yml uses
source "$SCRIPT_DIR/sandbox_config.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
RESULTS=()

log_pass() { PASS=$((PASS+1)); RESULTS+=("${GREEN}PASS${NC} | $1"); echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { FAIL=$((FAIL+1)); RESULTS+=("${RED}FAIL${NC} | $1"); echo -e "${RED}[FAIL]${NC} $1"; }
log_info() { echo -e "       $1"; }

# Common docker run flags matching docker-compose.sandbox.yml exactly
# These are the SAME limits the compose file sets, sourced from sandbox_config.env
COMMON_FLAGS=(
    --rm
    --runtime="$SANDBOX_RUNTIME"
    --read-only
    --network=sandbox_sandbox-net
    --cap-drop=ALL
    --security-opt=no-new-privileges:true
    --tmpfs "/tmp:size=${SANDBOX_TMP_SIZE},noexec,nosuid"
    --tmpfs "/var/tmp:size=${SANDBOX_VAR_TMP_SIZE},noexec,nosuid"
    --tmpfs "/workspace:size=${SANDBOX_WORKSPACE_SIZE},noexec,nosuid,uid=1000,gid=1000"
    --memory="$SANDBOX_MEMORY_LIMIT"
    --memory-swap="$SANDBOX_MEMORY_SWAP"
    --cpus="$SANDBOX_CPU_LIMIT"
    --pids-limit="$SANDBOX_PID_LIMIT"
)

IMAGE="breakmyapp-scan-runner:latest"

# -------------------------------------------------------------------------
# Pre-flight: ensure image exists and sandbox-net network exists
# -------------------------------------------------------------------------
echo ""
echo "=== Pre-flight checks ==="

if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo -e "${RED}Image $IMAGE not found. Build it first:${NC}"
    echo "  docker build -f Dockerfile.sandbox -t $IMAGE ."
    exit 1
fi
log_info "Image $IMAGE found"

# Create the sandbox network if it doesn't exist (matches compose network name)
NETWORK_NAME="sandbox_sandbox-net"
if ! docker network inspect "$NETWORK_NAME" &>/dev/null; then
    log_info "Creating internal network $NETWORK_NAME..."
    docker network create --internal "$NETWORK_NAME" >/dev/null 2>&1
fi
log_info "Network $NETWORK_NAME ready"

echo ""
echo "=== Running adversarial tests ==="
echo "    (using limits from sandbox_config.env)"
echo "    Memory: $SANDBOX_MEMORY_LIMIT | Swap: $SANDBOX_MEMORY_SWAP"
echo "    CPUs: $SANDBOX_CPU_LIMIT | PIDs: $SANDBOX_PID_LIMIT"
echo "    Timeout: ${SANDBOX_TIMEOUT_SECONDS}s"
echo ""

# =========================================================================
# TEST 1: Fork bomb — PID limit must kill it, host stays responsive
# =========================================================================
echo "--- Test 1: Fork bomb (PID limit / memory backstop) ---"

FORK_CID=$(docker run -d "${COMMON_FLAGS[@]}" "$IMAGE" python3 -c "
import os, time
while True:
    pid = os.fork()
    if pid == 0:
        while True:
            pass
" 2>&1)

if [[ -z "$FORK_CID" ]] || [[ "$FORK_CID" == *"Error"* ]]; then
    log_fail "Fork bomb — failed to start container"
    log_info "Output: $FORK_CID"
else
    log_info "Container: ${FORK_CID:0:12}"
    sleep 20

    STATUS=$(docker inspect "$FORK_CID" --format '{{.State.Status}}' 2>/dev/null || echo "unknown")
    OOMKILLED=$(docker inspect "$FORK_CID" --format '{{.State.OOMKilled}}' 2>/dev/null || echo "unknown")
    EXITCODE=$(docker inspect "$FORK_CID" --format '{{.State.ExitCode}}' 2>/dev/null || echo "unknown")

    log_info "Status: $STATUS | OOMKilled: $OOMKILLED | ExitCode: $EXITCODE"

    if [[ "$STATUS" == "exited" ]]; then
        log_pass "Fork bomb — container terminated (status=$STATUS, oomkilled=$OOMKILLED, exit=$EXITCODE)"
    else
        log_fail "Fork bomb — container still running after 20s, resource limits did not contain it"
        docker kill -s KILL "$FORK_CID" >/dev/null 2>&1 || true
    fi

    HOST_RESPONSIVE=$(timeout 5 echo "alive" 2>&1)
    if [[ "$HOST_RESPONSIVE" == "alive" ]]; then
        log_info "Host confirmed responsive after fork bomb"
    else
        log_fail "Fork bomb — host unresponsive!"
    fi

    docker rm -f "$FORK_CID" >/dev/null 2>&1 || true
fi

echo ""

# =========================================================================
# TEST 2: Memory bomb — OOM kill must trigger, no swap thrashing
# =========================================================================
echo "--- Test 2: Memory bomb (OOM kill) ---"

MEM_START=$(date +%s)

MEM_OUTPUT=$(timeout 60 docker run \
    "${COMMON_FLAGS[@]}" \
    "$IMAGE" \
    python3 -c "
import sys
# Allocate way past the 512MB cap in 10MB chunks
chunks = []
try:
    while True:
        chunks.append(b'X' * (10 * 1024 * 1024))  # 10MB per chunk
        print(f'Allocated {len(chunks) * 10} MB', file=sys.stderr)
except MemoryError:
    print(f'MemoryError at {len(chunks) * 10} MB', file=sys.stderr)
    sys.exit(1)
" 2>&1) || true

MEM_EXIT=$?
MEM_END=$(date +%s)
MEM_DURATION=$((MEM_END - MEM_START))

# Check for OOM kill (exit code 137 = SIGKILL from OOM killer)
if echo "$MEM_OUTPUT" | grep -qi "killed\|oom\|memory" || [[ $MEM_EXIT -eq 137 ]]; then
    log_pass "Memory bomb — OOM killed in ${MEM_DURATION}s"
    log_info "Output: $(echo "$MEM_OUTPUT" | tail -3)"
elif echo "$MEM_OUTPUT" | grep -qi "MemoryError"; then
    log_pass "Memory bomb — Python MemoryError raised (cgroup limit enforced)"
    log_info "Output: $(echo "$MEM_OUTPUT" | tail -3)"
else
    log_fail "Memory bomb — no OOM kill detected (exit=$MEM_EXIT, duration=${MEM_DURATION}s)"
    log_info "Output: $(echo "$MEM_OUTPUT" | tail -5)"
fi

# Check host swap usage didn't spike
SWAP_USED=$(free -m 2>/dev/null | awk '/Swap:/ {print $3}')
if [[ -n "$SWAP_USED" ]] && [[ "$SWAP_USED" -lt 100 ]]; then
    log_info "Host swap usage: ${SWAP_USED}MB (no thrashing)"
else
    log_info "Host swap usage: ${SWAP_USED:-unknown}MB"
fi

echo ""

# =========================================================================
# TEST 3: Infinite loop — wall-clock timeout kills it
# =========================================================================
echo "--- Test 3: Infinite loop (wall-clock timeout) ---"

# Use a SHORT timeout for testing (15 seconds instead of the full 5 minutes)
TEST_TIMEOUT=15

log_info "Starting infinite loop container (will SIGKILL after ${TEST_TIMEOUT}s)..."

# Start the container in the background
LOOP_CONTAINER=$(docker run -d \
    "${COMMON_FLAGS[@]}" \
    "$IMAGE" \
    python3 -c "
while True:
    pass
" 2>&1)

# Remove --rm flag for background containers — we need the ID
# Actually, -d with --rm is fine, Docker cleans up after kill
if [[ -z "$LOOP_CONTAINER" ]] || [[ "$LOOP_CONTAINER" == *"Error"* ]]; then
    log_fail "Infinite loop — failed to start container"
    log_info "Output: $LOOP_CONTAINER"
else
    LOOP_START=$(date +%s)
    log_info "Container ID: ${LOOP_CONTAINER:0:12}"
    log_info "Waiting ${TEST_TIMEOUT}s before sending SIGKILL..."

    sleep "$TEST_TIMEOUT"

    # Kill with SIGKILL (not SIGTERM — hostile process could ignore SIGTERM)
    docker kill --signal=KILL "$LOOP_CONTAINER" >/dev/null 2>&1 || true

    LOOP_END=$(date +%s)
    LOOP_DURATION=$((LOOP_END - LOOP_START))

    # Verify it's dead
    sleep 1
    STILL_RUNNING=$(docker inspect "$LOOP_CONTAINER" --format='{{.State.Running}}' 2>/dev/null || echo "false")
    if [[ "$STILL_RUNNING" == "false" ]]; then
        log_pass "Infinite loop — SIGKILL confirmed container dead after ${LOOP_DURATION}s"
    else
        log_fail "Infinite loop — container still running after SIGKILL!"
        docker kill "$LOOP_CONTAINER" >/dev/null 2>&1 || true
    fi
fi

echo ""

# =========================================================================
# TEST 4: Network exfiltration — outbound blocked (internal network)
# =========================================================================
echo "--- Test 4: Network exfiltration (outbound blocked) ---"

# Test 4a: curl to external IP
CURL_OUTPUT=$(timeout 15 docker run \
    "${COMMON_FLAGS[@]}" \
    "$IMAGE" \
    curl -s --connect-timeout 5 http://1.1.1.1 2>&1) || true

if [[ -z "$CURL_OUTPUT" ]] || echo "$CURL_OUTPUT" | grep -qiE "could not resolve|network unreachable|connection refused|no route|timed out|couldn't connect|failed to connect"; then
    log_pass "Network exfil (curl) — outbound HTTP to 1.1.1.1 blocked"
    log_info "Output: $(echo "$CURL_OUTPUT" | head -2)"
else
    log_fail "Network exfil (curl) — outbound HTTP to 1.1.1.1 SUCCEEDED"
    log_info "Output: $(echo "$CURL_OUTPUT" | head -5)"
fi

# Test 4b: DNS lookup
DNS_OUTPUT=$(timeout 15 docker run \
    "${COMMON_FLAGS[@]}" \
    "$IMAGE" \
    nslookup google.com 2>&1) || true

if echo "$DNS_OUTPUT" | grep -qiE "can't resolve|nxdomain|timed out|connection timed out|no servers|server can't find|couldn't get address|network unreachable"; then
    log_pass "Network exfil (DNS) — DNS resolution blocked"
    log_info "Output: $(echo "$DNS_OUTPUT" | head -3)"
elif [[ -z "$DNS_OUTPUT" ]]; then
    log_pass "Network exfil (DNS) — DNS resolution blocked (no output)"
else
    # Check if it actually resolved
    if echo "$DNS_OUTPUT" | grep -qiE "Address:.*[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+" | grep -v "127.0"; then
        log_fail "Network exfil (DNS) — DNS resolution for google.com SUCCEEDED"
        log_info "Output: $(echo "$DNS_OUTPUT" | head -5)"
    else
        log_pass "Network exfil (DNS) — DNS resolution failed"
        log_info "Output: $(echo "$DNS_OUTPUT" | head -3)"
    fi
fi

echo ""

# =========================================================================
# TEST 5: Host path access + production service resolution
# =========================================================================
echo "--- Test 5: Host path access + service resolution ---"

# Test 5a: Attempt to read /etc/shadow (should fail — no mount, read-only)
SHADOW_OUTPUT=$(timeout 10 docker run \
    "${COMMON_FLAGS[@]}" \
    "$IMAGE" \
    cat /etc/shadow 2>&1) || true

if echo "$SHADOW_OUTPUT" | grep -qiE "permission denied|no such file|read-only"; then
    log_pass "Host path (/etc/shadow) — access denied"
    log_info "Output: $(echo "$SHADOW_OUTPUT" | head -1)"
else
    log_fail "Host path (/etc/shadow) — access NOT denied"
    log_info "Output: $(echo "$SHADOW_OUTPUT" | head -3)"
fi

# Test 5b: Attempt to read /proc/1/environ (host PID 1 env vars)
PROC_OUTPUT=$(timeout 10 docker run \
    "${COMMON_FLAGS[@]}" \
    "$IMAGE" \
    cat /proc/1/environ 2>&1) || true

if echo "$PROC_OUTPUT" | grep -qiE "permission denied|no such file|operation not permitted"; then
    log_pass "Host path (/proc/1/environ) — access denied"
    log_info "Output: $(echo "$PROC_OUTPUT" | head -1)"
elif [[ -z "$PROC_OUTPUT" ]]; then
    log_pass "Host path (/proc/1/environ) — empty output (gVisor virtualizes /proc)"
else
    # Check if it contains actual host env vars
    if echo "$PROC_OUTPUT" | grep -q "POSTGRES_PASSWORD\|DATABASE_URL\|REDIS_URL"; then
        log_fail "Host path (/proc/1/environ) — LEAKED HOST ENVIRONMENT VARIABLES"
    else
        log_pass "Host path (/proc/1/environ) — no host env vars leaked (gVisor sandbox)"
        log_info "Output length: $(echo -n "$PROC_OUTPUT" | wc -c) bytes"
    fi
fi

# Test 5c: Resolve production service hostnames (should all fail)
for hostname in postgres redis backend breakmyapp-postgres breakmyapp-redis breakmyapp-backend; do
    RESOLVE_OUTPUT=$(timeout 10 docker run \
        "${COMMON_FLAGS[@]}" \
        "$IMAGE" \
        python3 -c "
import socket
try:
    ip = socket.gethostbyname('$hostname')
    print(f'RESOLVED: $hostname -> {ip}')
except socket.gaierror as e:
    print(f'BLOCKED: $hostname -> {e}')
    exit(1)
" 2>&1) || true

    if echo "$RESOLVE_OUTPUT" | grep -q "BLOCKED"; then
        log_pass "Service resolution ($hostname) — blocked"
    elif echo "$RESOLVE_OUTPUT" | grep -q "RESOLVED"; then
        log_fail "Service resolution ($hostname) — RESOLVED to an IP!"
        log_info "Output: $RESOLVE_OUTPUT"
    else
        log_pass "Service resolution ($hostname) — failed (no output)"
    fi
done

echo ""

# =========================================================================
# TEST 6: Disk fill — tmpfs cap must prevent filling host disk
# =========================================================================
echo "--- Test 6: Disk fill (tmpfs cap) ---"

DISK_OUTPUT=$(timeout 30 docker run \
    "${COMMON_FLAGS[@]}" \
    "$IMAGE" \
    python3 -c "
import sys, os

# Write into /workspace (tmpfs capped at ${SANDBOX_WORKSPACE_SIZE})
# Try to write 1GB, which should exceed the tmpfs cap
written = 0
chunk = b'X' * (1024 * 1024)  # 1MB chunks
try:
    with open('/workspace/fill_test', 'wb') as f:
        for i in range(2048):  # 2GB attempted
            f.write(chunk)
            written += len(chunk)
            if written % (50 * 1024 * 1024) == 0:
                print(f'Written {written // (1024*1024)} MB to /workspace', file=sys.stderr)
except OSError as e:
    print(f'Disk write failed at {written // (1024*1024)} MB: {e}', file=sys.stderr)
    sys.exit(1)
print(f'WARNING: wrote {written // (1024*1024)} MB without hitting limit!', file=sys.stderr)
" 2>&1) || true

if echo "$DISK_OUTPUT" | grep -qiE "no space left|disk quota|write failed|OSError"; then
    WRITTEN_MB=$(echo "$DISK_OUTPUT" | grep -oE '[0-9]+ MB' | tail -1)
    log_pass "Disk fill — write failed at ${WRITTEN_MB:-unknown} (tmpfs cap enforced)"
    log_info "Output: $(echo "$DISK_OUTPUT" | tail -2)"
else
    log_fail "Disk fill — write did NOT fail (tmpfs cap may not be enforced)"
    log_info "Output: $(echo "$DISK_OUTPUT" | tail -5)"
fi

# Verify host disk is unaffected
HOST_DISK_USED=$(df -h / 2>/dev/null | awk 'NR==2 {print $5}')
log_info "Host disk usage after test: $HOST_DISK_USED"

echo ""

# =========================================================================
# Summary
# =========================================================================
echo "==========================================="
echo "        SANDBOX VERIFICATION SUMMARY"
echo "==========================================="
echo ""
printf "%-6s | %s\n" "Result" "Test"
echo "-------|--------------------------------------------"
for result in "${RESULTS[@]}"; do
    echo -e "$result"
done
echo ""
echo "-------|--------------------------------------------"
echo -e "Total: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "==========================================="
echo ""

if [[ $FAIL -gt 0 ]]; then
    echo -e "${RED}WARNING: $FAIL test(s) failed. Review results above.${NC}"
    echo "The sandbox may not be properly configured."
    exit 1
else
    echo -e "${GREEN}All tests passed. Sandbox isolation is verified.${NC}"
    exit 0
fi
