#!/usr/bin/env bash
# Staging deploy with auto-rollback (SPEC D04-E). Runs ON THE VPS, invoked by
# .github/workflows/deploy-staging.yml after manual approval (or by hand):
#
#   SOPS_AGE_KEY_FILE=~/.config/sops/age/ci-key.txt \
#     bash scripts/deploy/staging_deploy.sh <git-sha>
#
# Flow: decrypt secrets -> pull images for <git-sha> -> compose up -> smoke
# (/health/deep + one page per app) -> record sha as last-good, or roll back
# to the previously recorded sha and exit non-zero.
set -euo pipefail

TAG="${1:?usage: staging_deploy.sh <git-sha>}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"

COMPOSE=(docker compose -p agri-staging -f docker-compose.staging.yml)
STATE_FILE=".staging-deployed" # last sha that passed smoke (gitignored)
SECRETS_FILE="secrets/staging.env"
SMOKE_RETRIES=30 # x 2s = 60s per endpoint

cleanup() {
  # never leave decrypted secrets on disk; compose containers already hold
  # their env, and the next deploy re-decrypts
  rm -f "$SECRETS_FILE"
}
trap cleanup EXIT

decrypt_secrets() {
  umask 077
  sops --decrypt "secrets/staging.sops.env" >"$SECRETS_FILE"
}

deploy() {
  local tag="$1"
  echo "deploy: bringing up agri-staging @ ${tag}"
  TAG="$tag" "${COMPOSE[@]}" pull --quiet
  TAG="$tag" "${COMPOSE[@]}" up -d --remove-orphans
}

wait_for() {
  local url="$1" attempt
  for ((attempt = 1; attempt <= SMOKE_RETRIES; attempt++)); do
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      echo "smoke OK: $url"
      return 0
    fi
    sleep 2
  done
  echo "smoke FAILED: $url (no 2xx after $((SMOKE_RETRIES * 2))s)"
  return 1
}

smoke() {
  # deep health hits postgres/redis/meili/minio through the API
  wait_for "http://localhost:8100/health/deep" || return 1
  local port
  for port in 3100 3101 3102 3103 3104; do # one page per app
    wait_for "http://localhost:${port}/" || return 1
  done
}

PREVIOUS="$(cat "$STATE_FILE" 2>/dev/null || true)"

decrypt_secrets
deploy "$TAG"

if smoke; then
  printf '%s\n' "$TAG" >"$STATE_FILE"
  echo "deploy: staging is healthy @ ${TAG}"
  exit 0
fi

echo "deploy: smoke failed for ${TAG}" >&2
if [[ -n "$PREVIOUS" && "$PREVIOUS" != "$TAG" ]]; then
  echo "deploy: rolling back to last-good ${PREVIOUS}" >&2
  deploy "$PREVIOUS"
  if smoke; then
    echo "deploy: rollback to ${PREVIOUS} is healthy" >&2
  else
    echo "deploy: ROLLBACK ALSO FAILED - staging needs a human" >&2
  fi
else
  echo "deploy: no last-good sha recorded - nothing to roll back to" >&2
fi
exit 1
