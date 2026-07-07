import os
import sqlite3


DB_PATH = os.path.join(os.path.dirname(__file__), "data", "veille.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    "Crée les tables/vues si besoin, puis applique les migrations (colonnes manquantes)."
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()
    with get_connection() as conn:
        conn.executescript(schema)
    migrer_db()
    print("Initialisation de la base")


# Colonnes attendues sur la table articles : nom -> définition SQL pour ADD COLUMN.
# Pour mettre à niveau une base existante SANS la recréer, on ajoute seulement
# celles qui manquent (ALTER TABLE ne touche pas aux données existantes).
COLONNES_ARTICLES = {
    "auteur":           "TEXT",
    "langue":           "TEXT",
    "resume":           "TEXT",
    "contenu":          "TEXT",
    "score_pertinence": "INTEGER DEFAULT 0",
    "score_details":    "TEXT",
    "llm_score":        "INTEGER",
    "llm_raison":       "TEXT",
    "llm_resume":       "TEXT",
}


def migrer_db():
    """ Ajoute les colonnes manquantes à 'articles' sans effacer les données. """
    conn = get_connection()
    try:
        existantes = {row["name"] for row in conn.execute("PRAGMA table_info(articles)")}
        ajoutees = []
        for nom, definition in COLONNES_ARTICLES.items():
            if nom not in existantes:
                conn.execute(f"ALTER TABLE articles ADD COLUMN {nom} {definition}")
                ajoutees.append(nom)
        if ajoutees:
            conn.commit()
            print(f"Migration : colonnes ajoutées -> {', '.join(ajoutees)}")
    finally:
        conn.close()


def upsert_source(source: dict):
    sql = """
        INSERT INTO sources (id, nom, url_rss, url_api, portee, pays, fiabilite)
        VALUES (:id, :nom, :url_rss, :url_api, :portee, :pays, :fiabilite)
        ON CONFLICT(id) DO UPDATE SET
            nom       = excluded.nom,
            url_rss   = excluded.url_rss,
            url_api   = excluded.url_api,
            portee    = excluded.portee,
            pays      = excluded.pays,
            fiabilite = excluded.fiabilite
    """
    conn = get_connection()
    try:
        with conn:
            conn.execute(sql, source)
    finally:
        conn.close()


def insert_article(article: dict):
    """INSERT OR IGNORE — ne remplace pas si l'URL existe déjà."""
    sql = """
        INSERT OR IGNORE INTO articles
            (id, source_id, auteur, date_publication, langue, titre, resume, contenu,
             score_pertinence, score_details, llm_score, llm_raison, llm_resume, url, created_at)
        VALUES
            (:id, :source_id, :auteur, :date_publication, :langue, :titre, :resume, :contenu,
             :score_pertinence, :score_details, :llm_score, :llm_raison, :llm_resume, :url, :created_at)
    """
    conn = get_connection()
    try:
        with conn:
            conn.execute(sql, article)
    finally:
        conn.close()


def get_articles(source_id: str = None, since: str = None, limit: int = None) -> list:
    sql = "SELECT a.*, s.nom as source_nom FROM articles a JOIN sources s ON s.id = a.source_id WHERE 1=1"
    params = []
    if source_id:
        sql += " AND a.source_id = ?"
        params.append(source_id)
    if since:
        sql += " AND a.created_at >= ?"
        params.append(since)
    sql += " ORDER BY a.created_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    conn = get_connection()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_contenu(article: dict):
    """ Met à jour le champ contenu d'un article déjà en base (par id). """
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "UPDATE articles SET contenu = :contenu WHERE id = :id",
                {"id": article["id"], "contenu": article.get("contenu")},
            )
    finally:
        conn.close()


def update_scores(article: dict):
    """ Met à jour les colonnes de score d'un article DÉJÀ en base (par id). """
    sql = """
        UPDATE articles SET
            score_pertinence = :score_pertinence,
            score_details    = :score_details,
            llm_score        = :llm_score,
            llm_raison       = :llm_raison,
            llm_resume       = :llm_resume
        WHERE id = :id
    """
    conn = get_connection()
    try:
        with conn:
            conn.execute(sql, {
                "id": article["id"],
                "score_pertinence": article.get("score_pertinence"),
                "score_details": article.get("score_details"),
                "llm_score": article.get("llm_score"),
                "llm_raison": article.get("llm_raison"),
                "llm_resume": article.get("llm_resume"),
            })
    finally:
        conn.close()


def get_articles_a_scorer() -> list:
    """ Articles pas encore scorés par le LLM (llm_score IS NULL). """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM articles WHERE llm_score IS NULL ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_coverage() -> list:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM couverture").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
