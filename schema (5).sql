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
    contenu          TEXT,
    score_pertinence INTEGER DEFAULT 0,
    score_details    TEXT,
    llm_score        INTEGER,
    llm_raison       TEXT,
    created_at       TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

-- Vue de couverture
-- date_publication est stocké au format MM/DD/YYYY (cf. parse_date).
-- On le reconvertit en ISO YYYY-MM-DD pour pouvoir trier/comparer.
CREATE VIEW IF NOT EXISTS couverture AS
SELECT
    s.id,
    s.nom,
    s.portee,
    s.pays,
    s.fiabilite,
    COUNT(a.id) AS nb_articles,
    MIN(
        substr(a.date_publication, 7, 4) || '-' ||
        substr(a.date_publication, 1, 2) || '-' ||
        substr(a.date_publication, 4, 2)
    ) AS premiere_publication,
    MAX(
        substr(a.date_publication, 7, 4) || '-' ||
        substr(a.date_publication, 1, 2) || '-' ||
        substr(a.date_publication, 4, 2)
    ) AS derniere_publication,
    MAX(a.created_at) AS dernier_ajout
FROM sources s
LEFT JOIN articles a
    ON a.source_id = s.id
    AND a.date_publication IS NOT NULL
    AND a.date_publication <> ''
GROUP BY s.id;
