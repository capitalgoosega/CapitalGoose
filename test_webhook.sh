#!/bin/bash
curl -X POST https://capitalgoose-production.up.railway.app/webhooks/zapier-application \
  -H "Content-Type: application/json" \
  -H "X-Capital-Goose-Webhook-Key: px6O9b-sVMnv0att9WAryS7kbbt7KsNzuOtG-edJgaE" \
  -d '{"Entry.Id":"test-002","Entry.FirstName":"Test","Entry.LastName":"User","Entry.EmailAddress":"test@example.com","Entry.LoanAmount":"10000","Entry.LoanType":"personal","Entry.DateOfBirth":"1990-01-01","Entry.Street":"123 Main St","Entry.City":"Atlanta","Entry.State":"GA","Entry.ZipCode":"30301"}'
