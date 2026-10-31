# Unified inbox reply workflows

The unified reply inbox groups signed inbound email replies with native Meta WhatsApp inbound messages by workspace prospect. Selecting a thread loads its channel-tagged history.

Workspace members can create a reply draft from the selected thread. The endpoint validates workspace membership, channel contact details, email suppression or documented WhatsApp opt-in and opt-out state, requires a current HTTPS source-evidence URL and an active campaign, and writes the draft to the existing pending-approval queue with a draft event. It never sends directly. Email replies continue through the existing SMTP delivery queue after approval; WhatsApp replies continue through the approved-template, account, consent, policy and quota-gated queue. Duplicate pending drafts are prevented by the existing database uniqueness constraint.

The inbox remains dependent on the inbound email webhook and Meta webhook processor being configured and running. Provider delivery and dispatch remain subject to live credentials, provider activation and workspace entitlements.
