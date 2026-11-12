# SSL Certificate Expiry

This runbook is for engineers who own internal services. It explains how TLS certificates are issued at Acme and what to do when one is about to expire.

## How certificates are issued

- Internal services (`*.acme.example` hosts that are not public) use certificates from the **Acme Internal CA**.
- Public websites use certificates managed by the Platform team through automated renewal.
- Request internal certificates in the Acme Service Portal under **Infrastructure > TLS Certificate**. Include the hostname, the service owner and the environment.
- Internal certificates are valid for **397 days**.

## Expiry alerts

The monitoring system checks every certificate daily and sends alerts to the service owner:

- **30 days** before expiry: email to the service owner.
- **14 days** before expiry: ticket opened automatically with severity SEV3.
- **3 days** before expiry: severity raised to SEV2 and the Platform on-call is paged.

## Renewing a certificate

1. Generate a new private key and CSR on the server. Never reuse the old private key and never send private keys by email or chat.
2. Submit the CSR in the same portal form and mark it as a **renewal**.
3. Install the new certificate together with the full chain (intermediate certificate included).
4. Reload the service and verify the new expiry date with `openssl s_client -connect host:443`.

## A certificate already expired

Users will see browser warnings and service-to-service calls will fail. Treat it as an incident: open a SEV2 ticket (SEV1 if a customer-facing system is down) and follow the renewal steps immediately. Users must not be told to click through certificate warnings.
