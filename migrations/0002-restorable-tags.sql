ALTER TABLE Tags DROP CONSTRAINT Tags_pkey;

ALTER TABLE Tags ADD CONSTRAINT Tags_pkey PRIMARY KEY (name, guild_id, deleted);
