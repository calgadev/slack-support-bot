# Incident Severity Definitions

Every incident ticket at Acme has a severity from SEV1 (most severe) to SEV4. The severity drives response times and who gets notified.

## SEV1 - Critical

A customer-facing system or a core business system is down for everyone, or there is an active security breach.

- Response time: **15 minutes**, 24x7.
- The on-call engineer and the Incident Manager are paged.
- Status updates every 30 minutes on `https://status.acme.example`.

## SEV2 - High

A major function is degraded, or a whole team or site cannot work, and there is no workaround. Lost or stolen devices and suspicious MFA prompts are SEV2.

- Response time: **1 hour**, 24x7.
- The on-call engineer is paged.

## SEV3 - Medium

A single user or a small group is affected, or a workaround exists.

- Response time: **4 business hours**.
- Most everyday problems (one laptop, one printer, one account) are SEV3.

## SEV4 - Low

Questions, minor issues, and requests that do not block work.

- Response time: **2 business days**.

## Choosing a severity

Pick the severity based on **impact and urgency**, not on how frustrated you are. If unsure, choose SEV3; the Service Desk will adjust the severity during triage. The bot and the portal map severities to priorities as follows: SEV1 = critical, SEV2 = high, SEV3 = medium, SEV4 = low.

Business hours are Monday to Friday, 08:00 to 18:00 local time.
