# MFA Issues

Acme uses multi-factor authentication (MFA) for VPN, email, the Acme Service Portal and AcmeERP. The approved method is the **Acme Authenticator** app with push notifications. SMS codes are a backup only.

## Setting up Acme Authenticator

1. Install Acme Authenticator from the Apple App Store or Google Play.
2. On your laptop, go to `https://mfa.acme.example` and sign in.
3. Choose **Add device** and scan the QR code with the app.
4. Approve the test notification.

## Not receiving push notifications

- Check that the phone has internet access and that notifications are allowed for Acme Authenticator.
- Open the app manually. Pending requests appear on the main screen.
- Make sure the phone's date and time are set automatically. A clock that is off by more than 2 minutes makes codes fail.
- As a fallback, use the 6-digit code shown in the app instead of the push.

## New phone or lost phone

- **New phone, old phone still works**: go to `https://mfa.acme.example`, choose **Add device**, register the new phone, then remove the old one.
- **Lost or stolen phone**: call the Service Desk at extension **4357** immediately. They will remove the device and give you a temporary access code valid for 24 hours so you can register a new phone.

## Suspicious MFA prompts

If you receive a push notification you did not trigger, **deny it** and report it right away by opening a ticket with severity SEV2 and choosing the category **Security**. Repeated unexpected prompts usually mean someone has your password, so reset your password as well.
