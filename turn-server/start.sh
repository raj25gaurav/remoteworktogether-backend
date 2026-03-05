#!/bin/sh
set -e

# Environment variables (set in Fly.io secrets):
#   TURN_SECRET  — shared secret for credential generation
#   TURN_REALM   — your domain or app name (e.g. "remoteworktogether")
#   FLY_PUBLIC_IP — set automatically by Fly.io

REALM="${TURN_REALM:-remoteworktogether}"
SECRET="${TURN_SECRET:-changeme_set_in_fly_secrets}"

echo "Starting coturn..."
echo "  Realm  : $REALM"
echo "  Ext IP : ${FLY_PUBLIC_IP:-auto}"

exec turnserver \
    --no-cli \
    --no-tls \
    --no-dtls \
    --listening-port=3478 \
    --min-port=49152 \
    --max-port=49200 \
    --realm="$REALM" \
    --use-auth-secret \
    --static-auth-secret="$SECRET" \
    --log-file=stdout \
    --verbose
