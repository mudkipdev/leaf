create table Tags
(
    name           VARCHAR(128),
    guild_id       BIGINT                                       not null,
    owner_id       BIGINT,
    content        TEXT                                         not null,
    created_at     TIMESTAMP default (NOW() AT TIME ZONE 'utc') not null,
    last_edited_at TIMESTAMP default (NOW() AT TIME ZONE 'utc') not null,
    uses           INTEGER   default 0                          not null,
    primary key (name, guild_id)
);

