-- Lutris's games table (the columns Lutris 0.5 creates), with four games.
-- The tests and the self-test build pga.db from this file.
CREATE TABLE games (
  id INTEGER PRIMARY KEY, name TEXT, slug TEXT, installer_slug TEXT, parent_slug TEXT,
  platform TEXT, runner TEXT, executable TEXT, directory TEXT, updated DATETIME,
  lastplayed INTEGER, installed INTEGER, installed_at INTEGER, year INTEGER, configpath TEXT,
  has_custom_banner INTEGER, has_custom_icon INTEGER, has_custom_coverart_big INTEGER,
  playtime REAL, hidden INTEGER, service TEXT, service_id TEXT, discord_id TEXT
);
INSERT INTO games (id, name, slug, platform, runner, directory, lastplayed, installed, playtime, service, configpath)
VALUES
  (1, 'Battle.net', 'battlenet', 'Windows', 'wine', '@HOME@/Games/battlenet', 1730000000, 1, 2.5, NULL, 'battlenet-1'),
  (2, 'Played Through Steam', 'played-through-steam', 'Linux', 'steam', '', 0, 1, 1.0, 'steam', NULL),
  (3, 'Not Installed', 'not-installed', 'Windows', 'wine', '', 0, 0, 0, NULL, NULL),
  (4, 'Lutris Example Brawler', 'lutris-example-brawler', 'Windows', 'wine', '@HOME@/Games/brawler', 0, 1, NULL, NULL, NULL);
