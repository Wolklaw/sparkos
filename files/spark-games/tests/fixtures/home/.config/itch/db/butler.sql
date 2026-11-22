-- The part of the itch app's butler.db that Spark Games reads (tables as butler creates them,
-- fewer columns). The tests and the self-test build butler.db from this file.
CREATE TABLE install_locations (id TEXT PRIMARY KEY, path TEXT, size INTEGER);
CREATE TABLE games (
  id INTEGER PRIMARY KEY, url TEXT, title TEXT, short_text TEXT, type TEXT,
  classification TEXT, cover_url TEXT, still_cover_url TEXT, created_at DATETIME,
  published_at DATETIME
);
CREATE TABLE caves (
  id TEXT PRIMARY KEY, game_id INTEGER, upload_id INTEGER, build_id INTEGER,
  installed_at DATETIME, last_touched_at DATETIME, seconds_run INTEGER, verdict TEXT,
  installed_size INTEGER, install_location_id TEXT, install_folder_name TEXT,
  custom_install_folder TEXT, pinned INTEGER
);
INSERT INTO install_locations VALUES ('loc-1', '@HOME@/.config/itch/apps', 0);
INSERT INTO games (id, title, classification) VALUES
  (101, 'Itch Example Hike', 'game'),
  (102, 'Pixel Font Pack', 'assets'),
  (103, 'Itch Example Jam Game', 'game');
INSERT INTO caves (id, game_id, last_touched_at, seconds_run, install_location_id,
                   install_folder_name, custom_install_folder) VALUES
  ('cave-a', 101, '2025-06-01 18:22:05.123456789+00:00', 5400, 'loc-1', 'itch-example-hike', NULL),
  ('cave-b', 102, NULL, 0, 'loc-1', 'pixel-font-pack', NULL),
  ('cave-c', 103, NULL, NULL, NULL, NULL, '@HOME@/Games/jam-game');
