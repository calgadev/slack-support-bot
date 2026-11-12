# Email Problems

Acme email runs on the company mail service, available in the desktop mail client and in webmail at `https://mail.acme.example`.

## Mailbox full

Each mailbox has a quota of **50 GB**. When you reach 45 GB you get a warning; at 50 GB you can no longer send email.

- Empty *Deleted Items* and *Junk*.
- Delete or save large attachments elsewhere (search for messages larger than 10 MB).
- Turn on the **Online Archive** in the mail client: messages older than 2 years are moved there automatically and do not count toward the quota.

## Cannot send or receive

1. Check webmail. If webmail works, the problem is your mail client: restart it, then remove and re-add the account.
2. If webmail does not work either, check `https://status.acme.example` for a known incident.
3. Messages larger than **25 MB** (including attachments) are rejected. Share large files through the shared drives instead.

## Phishing and suspicious email

Do not click links or open attachments in unexpected messages. Use the **Report Phishing** button in the mail client, which sends the message to the Security team and removes it from your inbox. If you already clicked a link or entered your password, reset your password immediately and open a SEV2 Security ticket.

## Shared mailboxes

Request access to a shared mailbox (for example `billing@acme.example`) in the Acme Service Portal under **Access Requests > Shared Mailbox**. The mailbox owner approves. The mailbox appears in your client within 2 hours after approval.

## Out-of-office replies

Set automatic replies in the mail client under *File > Automatic Replies* or in webmail under *Settings > Automatic replies*.
