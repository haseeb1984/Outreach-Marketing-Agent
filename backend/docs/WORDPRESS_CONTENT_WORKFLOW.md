# WordPress content workflow

The WordPress connector is workspace-scoped and uses WordPress Application Passwords over HTTPS.

## Setup

1. In WordPress, create a dedicated user for the integration.
2. Grant that user permission to edit and publish posts. Publishing permission is required for connection verification because the product supports an explicit publish action.
3. Open **Users → Profile → Application Passwords**, create an application password, and copy it once.
4. In the Outreach Marketing Agent dashboard, open **Editorial content workflow → WordPress connection**.
5. Enter the HTTPS site URL, WordPress username, and application password, then save and verify.
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
- Workspace authorization is enforced on every endpoint. Connection management and CMS actions require workspace admin/owner access.
- Application passwords are encrypted using AES-GCM with workspace and connection identifiers as authenticated additional data.
- Article Markdown is converted using an escaped, limited HTML subset. Raw HTML from article text is not passed through.
- The article's meta description is sent as the WordPress excerpt. SEO-plugin-specific metadata (Yoast, Rank Math, or other plugin fields) is not automatically written; plugin-specific integration remains separate work.
- Disconnecting removes the saved encrypted credential and does not delete posts already created on WordPress.
- WordPress provider actions are external side effects. A timeout can occur after WordPress has accepted a request; stable draft slugs allow the next draft attempt to find the existing draft.
