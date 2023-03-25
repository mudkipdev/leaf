CREATE TYPE infraction_type AS ENUM (
    'warning',
    'nickname_change'
    'voice_mute',
    'timeout',
    'kick',
    'ban'
);

CREATE SEQUENCE infraction_id_seq START 1;

CREATE TABLE IF NOT EXISTS infractions (
    id INTEGER DEFAULT nextval('infraction_id_seq'),
    guild_id BIGINT NOT NULL,
    member_id BIGINT NOT NULL,
    moderator_id BIGINT NOT NULL,
    type infraction_type NOT NULL,
    reason TEXT,
    hidden BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
    expires_at TIMESTAMP,
    PRIMARY KEY (id, guild_id)
);
