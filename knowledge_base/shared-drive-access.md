# Shared Drive Access

Departments at Acme store files on shared drives hosted on `files.acme.example`. Each department has a folder such as `\\files.acme.example\finance` or `\\files.acme.example\marketing`.

## Requesting access to a shared folder

1. In the Acme Service Portal choose **Access Requests > Shared Folder**.
2. Enter the folder path and the access level you need: **Read** or **Read/Write**.
3. The folder owner (usually the department head) approves the request.

Access is granted through security groups and takes effect after you **sign out and sign in again** on your laptop.

## Mapping a drive

- **Windows**: open File Explorer, right-click *This PC*, choose *Map network drive* and enter the folder path.
- **macOS**: in Finder press *Cmd + K* and enter `smb://files.acme.example/<folder>`.

You must be in the office or connected to VPN.

## "Access denied" errors

- If access was approved less than 1 hour ago, sign out and sign in again.
- Check that you are using the exact folder path from the approval email.
- Ask the folder owner to confirm you were added to the right group.

## Storage limits and recovery

Each department share has a quota of **2 TB**. Deleted files can be restored from snapshots taken every 4 hours and kept for **30 days**: right-click the folder, choose *Properties > Previous Versions* (Windows) or open a ticket (macOS).

Do not store personal files or customer data exports on shared drives.
