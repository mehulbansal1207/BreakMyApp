#!/usr/bin/env bash
# =========================================================================
# setup_gvisor.sh — Install and configure gVisor (runsc) on Ubuntu 22.04
#
# Run as root on the production droplet:
#   sudo ./setup_gvisor.sh
#
# This script:
#   1. Confirms cgroups v2
#   2. Checks kernel version for systrap support
#   3. Installs runsc from the official gVisor apt repository
#   4. Adds runsc as a NAMED Docker runtime (NOT the default)
#   5. Restarts Docker
#   6. Verifies gVisor is intercepting syscalls (not just starting containers)
# =========================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_ok()   { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC}  $1"; }
log_info() { echo -e "        $1"; }

ERRORS=0

# -------------------------------------------------------------------------
# 0. Must be root
# -------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    log_fail "This script must be run as root (sudo ./setup_gvisor.sh)"
    exit 1
fi

# -------------------------------------------------------------------------
# 1. Confirm cgroups v2
# -------------------------------------------------------------------------
echo ""
echo "=== Step 1: cgroups version check ==="
CGROUP_FS=$(stat -fc %T /sys/fs/cgroup 2>/dev/null || echo "unknown")
if [[ "$CGROUP_FS" == "cgroup2fs" ]]; then
    log_ok "cgroups v2 confirmed (filesystem type: $CGROUP_FS)"
else
    log_fail "cgroups v1 detected (filesystem type: $CGROUP_FS)"
    log_info "cgroups v1 has known bypass issues. Ubuntu 22.04 should use v2 by default."
    log_info "To switch: edit /etc/default/grub, add systemd.unified_cgroup_hierarchy=1"
    log_info "then: update-grub && reboot"
    ERRORS=$((ERRORS + 1))
fi

# -------------------------------------------------------------------------
# 2. Check kernel version for systrap support
# -------------------------------------------------------------------------
echo ""
echo "=== Step 2: Kernel version check (systrap support) ==="
KERNEL_VERSION=$(uname -r)
KERNEL_MAJOR=$(echo "$KERNEL_VERSION" | cut -d. -f1)
KERNEL_MINOR=$(echo "$KERNEL_VERSION" | cut -d. -f2)

log_info "Kernel: $KERNEL_VERSION"

# systrap needs kernel >= 4.1 (in practice, Ubuntu 22.04 ships 5.15+)
if [[ $KERNEL_MAJOR -gt 4 ]] || { [[ $KERNEL_MAJOR -eq 4 ]] && [[ $KERNEL_MINOR -ge 1 ]]; }; then
    log_ok "Kernel $KERNEL_VERSION is new enough for systrap"
else
    log_fail "Kernel $KERNEL_VERSION may be too old for systrap (need >= 4.1)"
    log_info "gVisor would silently fall back to ptrace mode, which is significantly slower."
    ERRORS=$((ERRORS + 1))
fi

# -------------------------------------------------------------------------
# 3. Check Docker storage driver and filesystem
# -------------------------------------------------------------------------
echo ""
echo "=== Step 3: Docker storage driver check ==="
STORAGE_DRIVER=$(docker info 2>/dev/null | grep -i "storage driver" | awk '{print $NF}')
DOCKER_FS=$(findmnt -no FSTYPE /var/lib/docker 2>/dev/null || echo "unknown")

log_info "Storage driver: ${STORAGE_DRIVER:-unknown}"
log_info "Filesystem at /var/lib/docker: ${DOCKER_FS}"

if [[ "$DOCKER_FS" == "xfs" ]]; then
    # Check for pquota mount option
    MOUNT_OPTS=$(findmnt -no OPTIONS /var/lib/docker 2>/dev/null || echo "")
    if echo "$MOUNT_OPTS" | grep -q "pquota"; then
        log_ok "xfs with pquota — storage_opt: size=XG will work for overlay caps"
        DISK_CAP_METHOD="storage_opt"
    else
        log_warn "xfs without pquota — storage_opt won't work, using tmpfs caps for disk limits"
        DISK_CAP_METHOD="tmpfs"
    fi
elif [[ "$DOCKER_FS" == "ext4" ]]; then
    log_warn "ext4 detected — storage_opt: size=XG is silently ignored on ext4"
    log_info "Disk limits will be enforced via capped tmpfs mounts instead."
    DISK_CAP_METHOD="tmpfs"
else
    log_warn "Filesystem '$DOCKER_FS' — storage_opt support is uncertain, using tmpfs caps"
    DISK_CAP_METHOD="tmpfs"
fi

echo "$DISK_CAP_METHOD" > /tmp/.gvisor_disk_cap_method

# -------------------------------------------------------------------------
# 4. Install gVisor (runsc)
# -------------------------------------------------------------------------
echo ""
echo "=== Step 4: Installing gVisor ==="

if command -v runsc &>/dev/null; then
    EXISTING_VERSION=$(runsc --version 2>&1 | head -1)
    log_info "runsc already installed: $EXISTING_VERSION"
    log_info "Reinstalling to ensure latest version..."
fi

# Official gVisor installation via apt
{
    set -x
    curl -fsSL https://gvisor.dev/archive.key | gpg --batch --yes --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" \
        > /etc/apt/sources.list.d/gvisor.list
    apt-get update -qq
    apt-get install -y -qq runsc
    set +x
} 2>&1 | while IFS= read -r line; do log_info "  $line"; done

RUNSC_PATH=$(command -v runsc)
if [[ -z "$RUNSC_PATH" ]]; then
    log_fail "runsc binary not found after installation"
    exit 1
fi
log_ok "runsc installed at $RUNSC_PATH"
log_info "Version: $(runsc --version 2>&1 | head -1)"

# -------------------------------------------------------------------------
# 5. Configure Docker daemon — add runsc as a NAMED runtime
# -------------------------------------------------------------------------
echo ""
echo "=== Step 5: Configuring Docker daemon ==="

DAEMON_JSON="/etc/docker/daemon.json"
RUNSC_LOG_DIR="/var/log/runsc"
mkdir -p "$RUNSC_LOG_DIR"

# Create or merge daemon.json
if [[ -f "$DAEMON_JSON" ]]; then
    log_info "Existing $DAEMON_JSON found, merging..."
    EXISTING=$(cat "$DAEMON_JSON")

    # Check if runsc is already configured
    if echo "$EXISTING" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'runsc' in d.get('runtimes',{}) else 1)" 2>/dev/null; then
        log_warn "runsc runtime already present in daemon.json — overwriting config"
    fi

    # Merge using python3 (available on Ubuntu 22.04)
    python3 -c "
import json, sys

with open('$DAEMON_JSON') as f:
    config = json.load(f)

config.setdefault('runtimes', {})
config['runtimes']['runsc'] = {
    'path': '$RUNSC_PATH',
    'runtimeArgs': [
        '--platform=systrap',
        '--network=sandbox',
        '--debug-log=$RUNSC_LOG_DIR/',
        '--debug'
    ]
}

# CRITICAL: Do NOT set 'default-runtime' to 'runsc'
# Production containers must stay on runc
if config.get('default-runtime') == 'runsc':
    del config['default-runtime']
    print('WARNING: Removed default-runtime=runsc to protect production containers', file=sys.stderr)

with open('$DAEMON_JSON', 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')

print(json.dumps(config, indent=2))
"
else
    log_info "No existing $DAEMON_JSON, creating new..."
    cat > "$DAEMON_JSON" <<DAEMONJSON
{
  "runtimes": {
    "runsc": {
      "path": "$RUNSC_PATH",
      "runtimeArgs": [
        "--platform=systrap",
        "--network=sandbox",
        "--debug-log=$RUNSC_LOG_DIR/",
        "--debug"
      ]
    }
  }
}
DAEMONJSON
    cat "$DAEMON_JSON"
fi

log_ok "Docker daemon configured with runsc as named runtime"

# Verify default-runtime is NOT runsc
DEFAULT_RT=$(python3 -c "
import json
with open('$DAEMON_JSON') as f:
    d = json.load(f)
print(d.get('default-runtime', 'runc'))
" 2>/dev/null || echo "runc")

if [[ "$DEFAULT_RT" == "runsc" ]]; then
    log_fail "CRITICAL: default-runtime is set to runsc! This would sandbox ALL containers."
    log_info "Removing default-runtime from daemon.json..."
    python3 -c "
import json
with open('$DAEMON_JSON') as f:
    d = json.load(f)
d.pop('default-runtime', None)
with open('$DAEMON_JSON', 'w') as f:
    json.dump(d, f, indent=2)
    f.write('\n')
"
    ERRORS=$((ERRORS + 1))
else
    log_ok "default-runtime is '$DEFAULT_RT' (production containers use runc)"
fi

# -------------------------------------------------------------------------
# 6. Restart Docker
# -------------------------------------------------------------------------
echo ""
echo "=== Step 6: Restarting Docker daemon ==="
systemctl restart docker
sleep 2

if systemctl is-active --quiet docker; then
    log_ok "Docker daemon restarted successfully"
else
    log_fail "Docker daemon failed to start after config change"
    log_info "Check: journalctl -u docker --no-pager -n 50"
    exit 1
fi

# -------------------------------------------------------------------------
# 7. Verify gVisor — run hello-world and check syscall interception
# -------------------------------------------------------------------------
echo ""
echo "=== Step 7: gVisor verification ==="

log_info "Running hello-world with --runtime=runsc..."
HELLO_OUTPUT=$(docker run --rm --runtime=runsc hello-world 2>&1) || {
    log_fail "docker run --runtime=runsc hello-world FAILED"
    log_info "Output: $HELLO_OUTPUT"

    # Check if systrap specifically failed
    if echo "$HELLO_OUTPUT" | grep -qi "systrap"; then
        log_fail "systrap platform initialization failed."
        log_info "This kernel may not support systrap. Do NOT silently fall back to ptrace."
        log_info "ptrace mode is significantly slower and you should be aware of it."
        log_info "To explicitly use ptrace, change --platform=systrap to --platform=ptrace in daemon.json"
    fi
    exit 1
}

if echo "$HELLO_OUTPUT" | grep -q "Hello from Docker"; then
    log_ok "hello-world container ran successfully under gVisor"
else
    log_fail "hello-world output unexpected: $HELLO_OUTPUT"
    ERRORS=$((ERRORS + 1))
fi

# Check runsc logs for syscall interception evidence
echo ""
log_info "Checking gVisor debug logs for syscall interception..."
sleep 1

RUNSC_LOGS=$(find "$RUNSC_LOG_DIR" -name "*.log" -newer /tmp/.gvisor_disk_cap_method 2>/dev/null | head -5)
if [[ -n "$RUNSC_LOGS" ]]; then
    SYSCALL_EVIDENCE=false
    for logfile in $RUNSC_LOGS; do
        # Look for Sentry boot or syscall handling evidence
        if grep -qiE "(sentry|syscall|sandbox started|platform started|systrap)" "$logfile" 2>/dev/null; then
            SYSCALL_EVIDENCE=true
            log_ok "Syscall interception confirmed in $logfile"
            log_info "Evidence:"
            grep -iE "(sentry|syscall|sandbox started|platform started|systrap)" "$logfile" 2>/dev/null | head -5 | while IFS= read -r line; do
                log_info "  $line"
            done
            break
        fi
    done

    if ! $SYSCALL_EVIDENCE; then
        log_warn "Log files found but no explicit syscall interception evidence"
        log_info "This may be normal — checking dmesg instead..."
    fi
else
    log_warn "No runsc log files found in $RUNSC_LOG_DIR"
    log_info "Checking dmesg for gVisor/runsc evidence..."
fi

# Also check dmesg
DMESG_EVIDENCE=$(dmesg 2>/dev/null | grep -i "runsc\|gvisor\|sentry" | tail -5)
if [[ -n "$DMESG_EVIDENCE" ]]; then
    log_ok "gVisor evidence found in dmesg:"
    echo "$DMESG_EVIDENCE" | while IFS= read -r line; do
        log_info "  $line"
    done
else
    log_info "No gVisor-specific dmesg entries (may be normal on newer kernels)"
fi

# Verify systrap specifically (not ptrace fallback)
echo ""
log_info "Checking platform mode..."
PLATFORM_LOG=$(find "$RUNSC_LOG_DIR" -name "*.log" -newer /tmp/.gvisor_disk_cap_method -exec grep -l "systrap\|ptrace" {} \; 2>/dev/null | head -1)
if [[ -n "$PLATFORM_LOG" ]]; then
    if grep -q "systrap" "$PLATFORM_LOG" 2>/dev/null; then
        log_ok "Platform: systrap (recommended)"
    elif grep -q "ptrace" "$PLATFORM_LOG" 2>/dev/null; then
        log_warn "Platform: ptrace (slower than systrap)"
        log_info "systrap may have failed to initialize. Check logs for details."
        log_info "This is NOT a silent fallback — you are being informed."
        ERRORS=$((ERRORS + 1))
    fi
else
    log_info "Could not determine platform mode from logs"
fi

# -------------------------------------------------------------------------
# 8. Confirm production containers are unaffected
# -------------------------------------------------------------------------
echo ""
echo "=== Step 8: Production container runtime check ==="

# Check if any running production containers accidentally use runsc
for container in breakmyapp-backend breakmyapp-worker breakmyapp-beat breakmyapp-postgres breakmyapp-redis breakmyapp-frontend; do
    RUNTIME=$(docker inspect "$container" --format '{{.HostConfig.Runtime}}' 2>/dev/null || echo "not-running")
    if [[ "$RUNTIME" == "not-running" ]]; then
        log_info "$container: not running (skip)"
    elif [[ "$RUNTIME" == "runsc" ]]; then
        log_fail "$container is using runsc! Production containers must use runc."
        ERRORS=$((ERRORS + 1))
    else
        # Empty string means default (runc)
        log_ok "$container: runtime=${RUNTIME:-runc} (correct)"
    fi
done

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
echo ""
echo "==========================================="
if [[ $ERRORS -eq 0 ]]; then
    echo -e "${GREEN}gVisor setup completed successfully with 0 errors.${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Build the sandbox image:  docker build -f sandbox/Dockerfile.sandbox -t breakmyapp-scan-runner:latest sandbox/"
    echo "  2. Run verification:         cd sandbox && ./verify_sandbox.sh"
else
    echo -e "${YELLOW}gVisor setup completed with $ERRORS warning(s)/error(s).${NC}"
    echo "Review the warnings above before proceeding."
fi
echo "==========================================="

# Cleanup
rm -f /tmp/.gvisor_disk_cap_method
