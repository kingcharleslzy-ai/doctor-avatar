#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-aliyun-doctor-avatar}"
SITE_URL="${SITE_URL:-https://liyong828.com}"

ssh "$HOST" 'bash /root/doctor-avatar/deploy/server/hermes-deploy-command'

printf '\n[hermes-local] Online health:\n'
curl -fsS --max-time 10 "${SITE_URL}/health"
printf '\n'

printf '\n[hermes-local] Rhinitis evidence stats:\n'
curl -fsS --max-time 10 "${SITE_URL}/api/rhinitis/evidence/stats"
printf '\n'
