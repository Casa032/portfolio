CREATE TABLE IF NOT EXISTS sources (
    id          TEXT PRIMARY KEY,
    nom         TEXT NOT NULL,
    url_rss     TEXT,
    url_api     TEXT,
    portee      TEXT,
    pays        TEXT,
    fiabilite   TEXT DEFAULT 'officielle',
    actif       INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS articles (
    id               TEXT PRIMARY KEY,
    source_id        TEXT NOT NULL,
    auteur           TEXT,
    titre            TEXT NOT NULL,
    url              TEXT UNIQUE NOT NULL,
    date_publication TEXT,
    langue           TEXT,
    resume           TEXT,
    created_at       TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE VIEW IF NOT EXISTS couverture AS
SELECT s.id, s.nom, s.portee, s.pays, s.fiabilite,
       COUNT(a.id) AS nb_articles,
       MAX(a.created_at) AS dernier_ajout
FROM sources s
LEFT JOIN articles a ON a.source_id = s.id
GROUP BY s.id;
