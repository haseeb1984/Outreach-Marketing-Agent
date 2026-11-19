# Account deletion and data retention

## Current account-deletion behavior

The authenticated `DELETE /api/v1/account` operation is an immediate, transactional account-access revocation and identity-pseudonymization workflow. It is not a claim that every copy of every record is erased instantly.

Within one database transaction, the service:

- locks the account and its related workspaces in deterministic order so membership/ownership changes serialize with deletion;
- refuses deletion if the account owns a workspace with another non-revoked member (active or suspended), requiring ownership transfer first;
- deletes sole-member workspaces owned by the account, relying on the workspace foreign-key cascade policy for tenant-owned application records;
- revokes all remaining memberships, active sessions and pending invitations issued by or addressed to the account;
- consumes outstanding email-verification and password-reset tokens;
- replaces the login email with a non-routable tombstone address, replaces the password with a newly generated hash, clears email verification, sets `status='deleted'` and records `deleted_at`;
- writes a security audit event without recording the original email address.

The operation does not silently delete a shared workspace or its shared business records. Other non-revoked members retain the workspace and its records. Attribution in shared operational history may remain associated with the pseudonymized account for audit integrity.

## Data categories and handling

| Data category | Deletion behavior |
| --- | --- |
| Login identity | Email replaced with a non-routable tombstone; password replaced; verification cleared; deletion timestamp recorded |
| Sessions and authentication tokens | Sessions revoked; verification and password-reset tokens consumed |
| Workspace memberships | Active and suspended memberships revoked |
| Pending workspace invitations | Invitations created by or addressed to the deleted account revoked |
| Sole-member owned workspace | Workspace and tenant-owned dependent records deleted through database cascades |
| Shared workspace | Retained for other non-revoked members; ownership transfer required if the deleting account is owner |
| Security audit history | Retained for security/accountability; identity reference remains pseudonymized |
| Billing and provider records | Not represented as fully erased by account deletion; retained as required for reconciliation, disputes, contracts or provider obligations |
| Backups and external providers | Outside the immediate transaction; governed by backup expiry and each provider's retention/deletion controls |

## Retention policy still requiring operator/legal approval

No single retention duration is hard-coded for audit events, billing evidence, backups, support records or provider-side data. Before accepting production customers, the service operator must approve a jurisdiction-aware schedule covering:

1. account and workspace operational data;
2. security audit and abuse-prevention records;
3. billing, invoice, tax and payment-provider evidence;
4. support requests and customer communications;
5. database backups, snapshots and disaster-recovery copies;
6. AI/search, email, WhatsApp and other connected-provider data.

The schedule must identify the purpose, system of record, retention period, deletion mechanism, backup expiry behavior, legal-hold exception and responsible operator for each category. Configure provider-side deletion and backup expiry consistently. Do not run a blanket database purge or cascade through shared workspaces as a substitute for this review.

## Release and verification notes

Migration `060_account_deletion_lifecycle.sql` adds `app_users.deleted_at`, backfills already deleted accounts from their last update timestamp, enforces status/timestamp consistency and indexes deleted accounts for future retention operations.

This migration is included in the release preflight. It must be applied through the approved migration process before deploying code that writes `deleted_at`. Production migration, backup expiry, provider deletion and legal retention review are separate operational approvals; none is implied by CI success.
