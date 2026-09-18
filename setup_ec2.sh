#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

log() {
    printf '\n[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run this script with sudo: sudo bash setup_ec2.sh" >&2
    exit 1
fi

if [[ ! -f /etc/os-release ]]; then
    echo "This script requires Ubuntu 22.04 or newer." >&2
    exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
    echo "This script supports Ubuntu only; detected ${ID:-unknown}." >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

log "Installing system prerequisites"
apt-get update
apt-get install -y ca-certificates curl gnupg lsb-release python3 python3-pip python3-venv

log "Configuring Docker's official Ubuntu repository"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable
EOF

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

log "Verifying installed tools"
docker --version
docker compose version
python3 --version

log "Running Python regression tests"
python3 -m unittest -v "$PROJECT_DIR/test_incident.py"

log "Building and starting the ERP OOM lab"
cd "$PROJECT_DIR"
docker compose up --build -d

log "Checking service health"
for attempt in {1..30}; do
    if curl -fsS http://127.0.0.1:8080/healthz >/dev/null; then
        break
    fi
    if [[ "$attempt" -eq 30 ]]; then
        docker compose logs --tail=100
        exit 1
    fi
    sleep 2
done

docker compose ps
curl -fsS http://127.0.0.1:8080/healthz
printf '\n\nService is running on port 8080.\n'
printf 'View logs:    cd %s && sudo docker compose logs -f\n' "$PROJECT_DIR"
printf 'View metrics: curl http://127.0.0.1:8080/metrics\n'