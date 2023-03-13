CREATE TABLE IF NOT EXISTS Tags (
    name VARCHAR(128),
    guild_id BIGINT NOT NULL,
    owner_id BIGINT,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    last_edited_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    uses INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (name, guild_id)
);