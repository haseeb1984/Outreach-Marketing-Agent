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

The integration uses a stable post slug derived from the content brief ID so a retry can recover a draft created before a network timeout. Concurrent send/publish requests are guarded by database status transitions.

## Security and limitations

- Only HTTPS sites on public host addresses are accepted; redirects are not followed and proxy environment settings are ignored.
- The configured site host is DNS-checked for public addresses before requests.
- Workspace authorization is enforced on every endpoint. Connection management and CMS actions require workspace admin/owner access. Project IDs are validated against the active workspace before a connection can be read, saved, verified or disconnected. Concurrent connection setup for the same workspace/project scope is serialized in PostgreSQL.
- Migration `068_project_scoped_wordpress_connections.sql` adds one connection per project plus one optional workspace-default connection. Existing workspace connections are preserved as the fallback during upgrade.
- Once an article is linked to a WordPress connection, retries and publication remain pinned to that exact connection even if another project or workspace-default connection is later added.
- Application passwords are encrypted using AES-GCM with workspace and connection identifiers as authenticated additional data.
- Article Markdown is converted using an escaped, limited HTML subset. Raw HTML from article text is not passed through.
- The article's meta description is sent as the WordPress excerpt. SEO-plugin-specific metadata (Yoast, Rank Math, or other plugin fields) is not automatically written; plugin-specific integration remains separate work.
- Disconnecting revokes the saved encrypted credential and does not delete posts already created on WordPress. Changing a connection's site URL is blocked once it has linked WordPress post IDs, preventing an old post ID from being accidentally updated or published on a different site. Configure another project connection when a workspace manages multiple websites.
- WordPress provider actions are external side effects. A timeout can occur after WordPress has accepted a request; stable draft slugs allow the next draft attempt to find the existing draft.
