#!/bin/bash
# Sends one fake intake to the old Zapier webhook. The key comes from your environment,
# never from this file:   CAPITAL_GOOSE_WEBHOOK_KEY=... ./scripts/test_zapier_webhook.sh
: "${CAPITAL_GOOSE_WEBHOOK_KEY:?set CAPITAL_GOOSE_WEBHOOK_KEY first}"
curl -X POST https://capitalgoose-production.up.railway.app/webhooks/zapier-application \
  -H "Content-Type: application/json" \
  -H "X-Capital-Goose-Webhook-Key: ${CAPITAL_GOOSE_WEBHOOK_KEY}" \
  -d '{"Entry.Id":"test-002","Entry.FirstName":"Test","Entry.LastName":"User","Entry.EmailAddress":"test@example.com","Entry.LoanAmount":"10000","Entry.LoanType":"personal","Entry.DateOfBirth":"1990-01-01","Entry.Street":"123 Main St","Entry.City":"Atlanta","Entry.State":"GA","Entry.ZipCode":"30301"}'
