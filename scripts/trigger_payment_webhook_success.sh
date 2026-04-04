#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <payment_intent_id> <amount_minor> [currency] [webhook_url] [webhook_secret]"
  echo "Example: $0 pi_123 16000 sgd http://localhost:5004/payment/webhook whsec_ticketblitz_local_demo"
  exit 1
fi

PAYMENT_INTENT_ID="$1"
AMOUNT_MINOR="$2"
CURRENCY="${3:-sgd}"
WEBHOOK_URL="${4:-http://localhost:5004/payment/webhook}"
WEBHOOK_SECRET="${5:-whsec_ticketblitz_local_demo}"

PAYLOAD=$(cat <<JSON
{
  "id": "evt_local_${PAYMENT_INTENT_ID}",
  "object": "event",
  "type": "payment_intent.succeeded",
  "data": {
    "object": {
      "id": "${PAYMENT_INTENT_ID}",
      "object": "payment_intent",
      "status": "succeeded",
      "amount_received": ${AMOUNT_MINOR},
      "currency": "${CURRENCY}",
      "latest_charge": "ch_local_${PAYMENT_INTENT_ID}"
    }
  }
}
JSON
)

TIMESTAMP=$(date +%s)
SIGNED_PAYLOAD="${TIMESTAMP}.${PAYLOAD}"
SIGNATURE=$(printf "%s" "$SIGNED_PAYLOAD" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $NF}')
STRIPE_SIGNATURE="t=${TIMESTAMP},v1=${SIGNATURE}"

curl -s -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: ${STRIPE_SIGNATURE}" \
  -d "$PAYLOAD" | jq
