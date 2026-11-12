# AcmeERP Access Errors

AcmeERP is Acme's internal resource planning system for purchasing, inventory and finance. It is available at `https://erp.acme.example` and requires VPN when you are outside the office.

## Requesting an AcmeERP role

Access in AcmeERP is role based (for example *Purchasing Viewer*, *Purchasing Approver*, *Finance Analyst*). Request roles in the Acme Service Portal under **Access Requests > AcmeERP Role**. Both your manager and the role owner must approve. Expect up to 3 business days.

## Error ERP-401 "Not authorized"

You are signed in but do not have the role needed for that screen.

- Check which role the screen requires in the error details.
- Request the missing role as described above.
- If you had access yesterday and lost it, your role may have been removed by the quarterly access review. Ask your manager to re-request it.

## Error ERP-403 "Session blocked"

Your session was blocked because you signed in from two places at once. Close all AcmeERP browser tabs, wait 5 minutes and sign in again from a single browser.

## Error ERP-503 "Service unavailable"

AcmeERP is down or in maintenance. Planned maintenance happens every **Sunday from 02:00 to 04:00 UTC**. Outside that window, check the status page at `https://status.acme.example`. If there is no known incident, open a ticket; an ERP outage affecting a whole team is usually SEV2.

## Page loads but data is missing

Clear the browser cache or try a private window. AcmeERP supports the latest versions of Chrome and Edge only.
