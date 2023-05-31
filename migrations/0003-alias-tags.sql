-- Create a new temporary table with the desired schema
CREATE TABLE IF NOT EXISTS Tags_temp (
    name VARCHAR(128) NOT NULL,
    guild_id BIGINT NOT NULL,
    owner_id BIGINT,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    last_edited_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    uses INTEGER NOT NULL DEFAULT 0,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    id SERIAL PRIMARY KEY,
    original_tag_id BIGINT
);

-- Copy data from the old table to the new table
INSERT INTO Tags_temp (name, guild_id, owner_id, content, created_at, last_edited_at, uses, deleted)
SELECT name, guild_id, owner_id, content, created_at, last_edited_at, uses, deleted FROM Tags;

-- Drop the old table
DROP TABLE Tags;

-- Rename the temporary table to the original table name
ALTER TABLE Tags_temp RENAME TO Tags;


