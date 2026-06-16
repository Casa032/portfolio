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
    "Crée la table si elle n'existe pas"
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()
    with get_connection() as conn:
        conn.executescript(schema)
    print("Initialisation de la base")


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
            (id, source_id, auteur, date_publication, langue, titre, resume, contenu, url, created_at)
        VALUES
            (:id, :source_id, :auteur, :date_publication, :langue, :titre, :resume, :contenu, :url, :created_at)
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


def get_coverage() -> list:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM couverture").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
