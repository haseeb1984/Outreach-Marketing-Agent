# Product Quality Standards

These standards are release requirements for the public website and authenticated dashboard. They are targets to verify, not claims that the current repository already meets them. The current repository has a basic API and no implemented frontend, so UI-specific checks remain pending until a frontend exists.

## 1. Accessibility: WCAG 2.2 Level AA

- Target WCAG 2.2 AA for all user-facing flows, including onboarding, project and campaign management, lead review, draft approval, settings, and error/recovery states.
- Use semantic HTML landmarks, a logical heading hierarchy, descriptive page titles, and correctly associated form labels and instructions.
- All functionality must be operable by keyboard alone; provide visible focus indicators, logical focus order, skip navigation, and no keyboard traps.
- Support screen readers with accessible names, roles, states, status announcements, and useful validation/error messages. Do not rely on color, position, or icons alone to communicate meaning.
- Meet WCAG contrast requirements: generally 4.5:1 for normal text and 3:1 for large text and relevant UI components/focus indicators.
- Ensure reflow and zoom at 200% without loss of content or functionality; test narrow mobile viewports and WCAG 2.2 target-size requirements.
- Respect reduced-motion preferences; avoid flashing content and unnecessary animation.
- Every important flow needs manual keyboard and screen-reader review in addition to automated scanning. Automated tools alone cannot certify WCAG conformance.

## 2. Accessibility verification

- Add automated axe-core or equivalent accessibility scans to UI tests when a frontend is introduced.
- Test representative pages and states, including validation errors, dialogs, navigation menus, tables, empty/loading states, and approval flows.
- Use automated checks plus manual keyboard testing and at least one screen-reader/browser combination before release.
- Release blocker: any known critical accessibility barrier in a core task; no unresolved serious/critical automated findings without documented triage and an approved remediation plan.

## 3. Technical SEO

SEO applies to intended public marketing/documentation pages only. Authenticated dashboard, account, project, campaign, lead, and private report pages must not be indexed.

- Public pages must return the correct HTTP status, have a unique descriptive title and meta description, one clear primary heading, useful original content, and descriptive link text.
- Use crawlable standard links, canonical URLs where appropriate, correct language metadata, and consistent HTTPS URLs.
- Provide a valid XML sitemap containing only canonical, indexable public URLs; provide robots.txt that does not accidentally block required public assets or expose private content.
- Add structured data only when it accurately describes visible page content and complies with the relevant schema guidelines. Never fabricate reviews, ratings, or business claims.
- Prevent indexing of authenticated/private routes using appropriate authentication and noindex directives where applicable; robots.txt alone is not access control.
- Verify redirects, 404/410 behavior, canonicalization, metadata, sitemap validity, and mobile rendering in automated checks and a staging crawl.
- Do not promise search rankings; validate technical eligibility and content quality.

## 4. Speed and Core Web Vitals

Target the "good" Core Web Vitals thresholds at the 75th percentile of real user visits:
- Largest Contentful Paint (LCP): 2.5 seconds or less.
- Interaction to Next Paint (INP): 200 milliseconds or less.
- Cumulative Layout Shift (CLS): 0.1 or less.

Additional performance requirements:
- Establish a Lighthouse CI baseline for representative public pages and dashboard flows once the frontend exists. Target scores of at least 90 for Performance, Accessibility, SEO, and Best Practices on representative production-like runs; investigate variance and do not treat a single lab score as proof of real-user performance.
- Optimize images (responsive sizing, modern formats when supported, explicit dimensions, lazy-load below-the-fold images), fonts, caching, compression, and static asset delivery.
- Minimize JavaScript and CSS, avoid unnecessary client-side libraries, split code by route where appropriate, and defer non-critical work.
- Avoid layout shifts from images, fonts, ads, and asynchronous UI. Provide loading states that preserve layout.
- Set measurable API budgets: bounded timeouts, pagination for collections, database indexes based on query patterns, and no unbounded synchronous work in request handlers.
- Measure before and after performance changes. Do not claim a speed improvement without repeatable measurements.

## 5. Responsive design and usability

- Support mobile, tablet, laptop, and wide desktop layouts without horizontal overflow in normal use.
- Core workflows must have clear labels, understandable confirmation/error messages, safe defaults, and recoverable failures.
- Tables and dense data must remain usable on small screens; provide alternatives where a wide table cannot reflow.
- Forms must preserve entered data after correctable validation errors where safe.

## 6. Security and privacy remain mandatory

- These quality standards do not override docs/SAFETY_AND_COMPLIANCE.md.
- Never expose private prospect data, tokens, account details, or dashboard content to crawlers or analytics tools.
- Apply authorization server-side; a hidden link or noindex is not an access-control mechanism.
- Do not load third-party scripts or fonts without evaluating privacy, security, performance, and consent implications.
- Any critical/high security release blocker remains a blocker even when visual, SEO, or performance scores are high.

## 7. Required release evidence

Before describing the frontend as production-ready, record:
1. Build and automated test results.
2. Automated accessibility scan results plus manual keyboard/screen-reader review.
3. SEO crawl results, sitemap/robots validation, and checks that private routes are not indexable.
4. Lighthouse results from repeatable production-like runs.
5. Real-user Core Web Vitals evidence when sufficient field data exists; until then, clearly label lab data as lab data.
6. Responsive layout and browser smoke-test results.
7. Security tests and the relevant review evidence.

Do not report a standard as "passed" unless the corresponding checks were actually run and their results recorded.
