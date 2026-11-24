# WordPress content workflow

The WordPress connector supports project-scoped connections with an optional workspace-level fallback and uses WordPress Application Passwords over HTTPS.

## Setup

1. In WordPress, create a dedicated user for the integration.
2. Grant that user permission to edit and publish posts. Publishing permission is required for connection verification because the product supports an explicit publish action.
3. Open **Users → Profile → Application Passwords**, create an application password, and copy it once.
4. In the Outreach Marketing Agent dashboard, open **Editorial content workflow → WordPress connection**.
5. Choose **Workspace default site** or a specific client project in the scope selector. Enter the HTTPS site URL, WordPress username, and application password, then save and verify. Project-specific connections take priority for each article transfer; the workspace default is used only when no project-specific connection record exists. If a project-specific connection is present but not verified, transfers fail closed instead of silently using another site. When a project has no exact connection, its settings view shows the inherited workspace-default connection as read-only; it cannot be disconnected from project scope. The selector manages connection settings, while article delivery resolves the correct project connection from the saved brief.
6. The application password is encrypted at rest with the configured provider credential encryption key. It is never returned by the API.

## Article lifecycle

1. A growth recommendation becomes a saved editorial brief.
2. A workspace admin approves the brief.
3. The article draft is generated and edited in the dashboard.
4. A workspace admin approves the article.
5. **Send to WordPress as draft** creates a WordPress post with status `draft`. It is not publicly visible.
6. A separate **Publish publicly on WordPress** action requires an explicit browser confirmation and server-side confirmation flag. Only then is the post changed to `publish`.

The integration uses a stable post slug derived from the content brief ID so a retry can recover a draft created before a network timeout. Concurrent send/publish requests are guarded by database status transitions. Draft delivery locks the selected connection while atomically pinning the brief to it, so a simultaneous credential/site update cannot move the connection to another website between selection and the first delivery attempt. Public publishing also locks the pinned connection while claiming the publish operation, so a concurrent disconnect or credential update cannot invalidate the connection between selection and the publish claim.

## Security and limitations

- Only HTTPS sites on public host addresses are accepted; redirects are not followed and proxy environment settings are ignored.
- Every request resolves all A/AAAA records, rejects any non-public answer, then connects directly to a validated IP literal while preserving the original Host header and TLS SNI/certificate hostname. This prevents a second DNS lookup from rebinding the connection to a private address.
- Workspace authorization is enforced on every endpoint. Connection management and CMS actions require workspace admin/owner access. Project IDs are validated against the active workspace before a connection can be read, saved, verified or disconnected. Concurrent connection setup for the same workspace/project scope is serialized in PostgreSQL.
- Migration `068_project_scoped_wordpress_connections.sql` adds one connection per project plus one optional workspace-default connection. Existing workspace connections are preserved as the fallback during upgrade.
- Once an article is linked to a WordPress connection, retries and publication remain pinned to that exact connection even if another project or workspace-default connection is later added.
- Application passwords are encrypted using AES-GCM with workspace and connection identifiers as authenticated additional data.
- Article Markdown is converted using an escaped, limited HTML subset. Raw HTML from article text is not passed through.
- The article's meta description is sent as the WordPress excerpt. SEO-plugin-specific metadata (Yoast, Rank Math, or other plugin fields) is not automatically written; plugin-specific integration remains separate work.
- Disconnecting revokes the saved encrypted credential and does not delete posts already created on WordPress. An unpinned project-specific override is deleted so new articles can inherit the workspace default; if any article is already pinned to that connection, the record is retained in a disabled state and the project continues to fail closed until reconnected. Changing a connection's site URL is blocked as soon as any article is pinned to it, including a delivery attempt that ended ambiguously before a post ID was saved. A timeout may occur after WordPress accepts a draft, so preserving the original site identity is necessary for safe slug-based recovery and prevents retries from creating duplicates on another site. Configure another project connection when a workspace manages multiple websites.
- WordPress provider actions are external side effects. A timeout can occur after WordPress has accepted a request; stable draft slugs allow the next draft attempt to find the existing draft.
