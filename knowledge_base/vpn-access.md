# VPN Access

Acme employees use **Acme SecureConnect** to reach internal systems from outside the office. This runbook covers requesting access, installing the client and fixing common connection problems.

## Who needs VPN access

You need VPN access to reach internal systems such as AcmeERP, the shared drives and the intranet when you are not connected to the office network. Webmail and the Acme Service Portal work without VPN.

Contractors get VPN access only when their sponsoring manager requests it, and their access expires after 90 days unless renewed.

## Requesting VPN access

1. Open the Acme Service Portal at `https://help.acme.example`.
2. Choose **Access Requests > VPN Access**.
3. Your manager approves the request. Access is usually active within 1 business day after approval.

## Installing Acme SecureConnect

- Company laptops already have Acme SecureConnect installed. Look for the blue shield icon in the system tray or menu bar.
- If it is missing, install it from the **Acme Software Center** (Windows) or **Acme Self Service** (macOS). Do not download VPN clients from the internet.
- Server address: `vpn.acme.example`.

## Connecting

1. Open Acme SecureConnect and enter `vpn.acme.example` if it is not filled in.
2. Sign in with your Acme username and password.
3. Approve the push notification in **Acme Authenticator** (see the MFA Issues article).

Sessions disconnect automatically after 12 hours. Reconnect if that happens.

## Troubleshooting connection errors

- **"Authentication failed"**: check that your password has not expired. Reset it with the self-service password portal if needed.
- **"MFA timeout"**: you must approve the push within 60 seconds. Make sure your phone has internet access.
- **Connected but internal sites do not load**: disconnect, wait 30 seconds and reconnect. If it still fails, restart the laptop.
- **Error SC-1020 "Device not compliant"**: your laptop is missing security updates. Install pending updates, restart, and try again.
- Hotel or airport Wi-Fi sometimes blocks VPN traffic. Try a phone hotspot to confirm.

If none of these steps work, open a ticket with the error message and a screenshot.
