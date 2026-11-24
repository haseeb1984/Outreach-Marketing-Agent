-- Persist generated SEO article drafts without publishing to a customer CMS.
ALTER TABLE website_content_briefs
    ADD COLUMN IF NOT EXISTS article_title TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS meta_title TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS meta_description TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS article_outline JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS internal_link_suggestions JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS article_body TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS article_status TEXT NOT NULL DEFAULT 'not_generated'
        CHECK (article_status IN ('not_generated','draft','in_review','approved','rejected')),
    ADD COLUMN IF NOT EXISTS article_generated_at TIMESTAMPTZ;
