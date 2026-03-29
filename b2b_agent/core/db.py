"""SQLite : schema, CRUD, métriques.

Chaque client a sa propre base de données SQLite.
Le client connecté est stocké dans st.session_state["client_id"].
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional
from .models import Prospect, ProspectStatus, Channel, SendResult

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Base par défaut (admin ou pas de client connecté)
_DEFAULT_DB = DATA_DIR / "agent.db"


def _get_db_path() -> Path:
    """Retourne le chemin de la DB du client connecté."""
    try:
        import streamlit as st
        client_id = st.session_state.get("client_id", "")
        if client_id and client_id != "admin":
            return DATA_DIR / f"client_{client_id}.db"
    except Exception:
        pass
    return _DEFAULT_DB


def get_conn() -> sqlite3.Connection:
    """Retourne une connexion SQLite avec row_factory."""
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Crée les tables si elles n'existent pas."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS prospects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            company TEXT NOT NULL,
            email TEXT,
            linkedin_url TEXT,
            role TEXT,
            company_size TEXT,
            industry TEXT,
            custom_signal TEXT,
            linkedin_headline TEXT,
            linkedin_about TEXT,
            recent_activity TEXT,
            skills TEXT,
            experience_summary TEXT,
            pain_points TEXT,
            mutual_context TEXT,
            tone_preference TEXT,
            status TEXT DEFAULT 'new',
            score INTEGER DEFAULT 0,
            current_step INTEGER DEFAULT 0,
            ab_variant TEXT,
            last_contacted_at TEXT,
            channel TEXT DEFAULT 'email',
            personalization_brief TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS prospect_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id TEXT NOT NULL,
            from_email TEXT,
            subject TEXT DEFAULT '',
            body TEXT DEFAULT '',
            detected_at TEXT DEFAULT (datetime('now')),
            draft_response TEXT,
            approval_status TEXT DEFAULT 'pending',
            approved_at TEXT,
            sent_at TEXT,
            FOREIGN KEY (prospect_id) REFERENCES prospects(id)
        );

        CREATE INDEX IF NOT EXISTS idx_replies_prospect ON prospect_replies(prospect_id);
        CREATE INDEX IF NOT EXISTS idx_replies_status ON prospect_replies(approval_status);

        CREATE TABLE IF NOT EXISTS send_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            step INTEGER NOT NULL,
            status TEXT NOT NULL,
            message_subject TEXT DEFAULT '',
            message_preview TEXT DEFAULT '',
            error TEXT,
            ab_variant TEXT,
            sent_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (prospect_id) REFERENCES prospects(id)
        );

        CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(status);
        CREATE INDEX IF NOT EXISTS idx_prospects_score ON prospects(score);
        CREATE INDEX IF NOT EXISTS idx_send_results_prospect ON send_results(prospect_id);
    """)

    # Migration : ajouter les colonnes de profil si elles n'existent pas (pour les DB existantes)
    profile_columns = [
        ("linkedin_headline", "TEXT"),
        ("linkedin_about", "TEXT"),
        ("recent_activity", "TEXT"),
        ("skills", "TEXT"),
        ("experience_summary", "TEXT"),
        ("pain_points", "TEXT"),
        ("mutual_context", "TEXT"),
        ("tone_preference", "TEXT"),
        ("personalization_brief", "TEXT"),
    ]
    existing = {row[1] for row in conn.execute("PRAGMA table_info(prospects)").fetchall()}
    for col_name, col_type in profile_columns:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE prospects ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()


def upsert_prospect(p: Prospect):
    """Insère ou met à jour un prospect (dédoublonné par email ou linkedin_url)."""
    conn = get_conn()
    existing = None
    if p.email:
        row = conn.execute("SELECT id FROM prospects WHERE email = ?", (p.email,)).fetchone()
        if row:
            existing = row["id"]
    if not existing and p.linkedin_url:
        row = conn.execute("SELECT id FROM prospects WHERE linkedin_url = ?", (p.linkedin_url,)).fetchone()
        if row:
            existing = row["id"]

    if existing:
        conn.execute("""
            UPDATE prospects SET name=?, company=?, email=?, linkedin_url=?, role=?,
            company_size=?, industry=?, custom_signal=?, channel=?,
            linkedin_headline=?, linkedin_about=?, recent_activity=?,
            skills=?, experience_summary=?, pain_points=?,
            mutual_context=?, tone_preference=?
            WHERE id=?
        """, (p.name, p.company, p.email, p.linkedin_url, p.role,
              p.company_size, p.industry, p.custom_signal, p.channel.value,
              p.linkedin_headline, p.linkedin_about, p.recent_activity,
              p.skills, p.experience_summary, p.pain_points,
              p.mutual_context, p.tone_preference, existing))
    else:
        conn.execute("""
            INSERT INTO prospects (id, name, company, email, linkedin_url, role,
            company_size, industry, custom_signal,
            linkedin_headline, linkedin_about, recent_activity,
            skills, experience_summary, pain_points,
            mutual_context, tone_preference,
            status, score, current_step, ab_variant, channel, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (p.id, p.name, p.company, p.email, p.linkedin_url, p.role,
              p.company_size, p.industry, p.custom_signal,
              p.linkedin_headline, p.linkedin_about, p.recent_activity,
              p.skills, p.experience_summary, p.pain_points,
              p.mutual_context, p.tone_preference,
              p.status.value, p.score, p.current_step, p.ab_variant,
              p.channel.value, p.created_at.isoformat()))
    conn.commit()
    conn.close()


def update_personalization_brief(prospect_id: str, brief: str):
    """Stocke le brief de personnalisation généré par le profile analyzer."""
    conn = get_conn()
    conn.execute(
        "UPDATE prospects SET personalization_brief = ? WHERE id = ?",
        (brief, prospect_id),
    )
    conn.commit()
    conn.close()


def get_all_prospects(status_filter: Optional[str] = None, min_score: int = 0) -> list[dict]:
    """Récupère tous les prospects, optionnellement filtrés."""
    conn = get_conn()
    query = "SELECT * FROM prospects WHERE score >= ?"
    params: list = [min_score]
    if status_filter and status_filter != "all":
        query += " AND status = ?"
        params.append(status_filter)
    query += " ORDER BY score DESC, created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_prospect_by_id(prospect_id: str) -> Optional[dict]:
    """Récupère un prospect par ID."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_prospect_by_email(email: str) -> Optional[dict]:
    """Récupère un prospect par email."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM prospects WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_prospect_status(prospect_id: str, status: str, **kwargs):
    """Met à jour le statut d'un prospect + champs optionnels."""
    conn = get_conn()
    sets = ["status = ?"]
    params = [status]
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        params.append(v)
    params.append(prospect_id)
    conn.execute(f"UPDATE prospects SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    conn.close()


def insert_send_result(sr: SendResult):
    """Enregistre un résultat d'envoi."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO send_results (prospect_id, channel, step, status,
        message_subject, message_preview, error, ab_variant, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (sr.prospect_id, sr.channel, sr.step, sr.status,
          sr.message_subject, sr.message_preview, sr.error,
          sr.ab_variant, sr.sent_at.isoformat()))
    conn.commit()
    conn.close()


def get_send_results(prospect_id: Optional[str] = None) -> list[dict]:
    """Récupère les résultats d'envoi."""
    conn = get_conn()
    if prospect_id:
        rows = conn.execute(
            "SELECT * FROM send_results WHERE prospect_id = ? ORDER BY sent_at DESC",
            (prospect_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM send_results ORDER BY sent_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_prospects_by_status() -> dict[str, int]:
    """Compte les prospects par statut."""
    conn = get_conn()
    rows = conn.execute("SELECT status, COUNT(*) as cnt FROM prospects GROUP BY status").fetchall()
    conn.close()
    return {r["status"]: r["cnt"] for r in rows}


def get_eligible_prospects(min_score: int = 40) -> list[dict]:
    """Prospects éligibles : score >= seuil, statut new/enriched/scored."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM prospects
        WHERE score >= ? AND status IN ('new', 'enriched', 'scored')
        ORDER BY score DESC
    """, (min_score,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_total_prospects() -> int:
    """Nombre total de prospects."""
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM prospects").fetchone()
    conn.close()
    return row["cnt"]


# --- Gestion des réponses prospects ---

def insert_reply(prospect_id: str, from_email: str, subject: str, body: str) -> int:
    """Enregistre une réponse de prospect. Retourne l'ID de la reply."""
    conn = get_conn()
    cursor = conn.execute("""
        INSERT INTO prospect_replies (prospect_id, from_email, subject, body)
        VALUES (?, ?, ?, ?)
    """, (prospect_id, from_email, subject, body))
    reply_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return reply_id


def save_draft_response(reply_id: int, draft: str):
    """Stocke le brouillon de réponse A-C-A."""
    conn = get_conn()
    conn.execute(
        "UPDATE prospect_replies SET draft_response = ? WHERE id = ?",
        (draft, reply_id),
    )
    conn.commit()
    conn.close()


def approve_reply(reply_id: int):
    """Marque une réponse comme approuvée par la coach."""
    conn = get_conn()
    conn.execute(
        "UPDATE prospect_replies SET approval_status = 'approved', approved_at = datetime('now') WHERE id = ?",
        (reply_id,),
    )
    conn.commit()
    conn.close()


def reject_reply(reply_id: int):
    """Marque une réponse comme rejetée."""
    conn = get_conn()
    conn.execute(
        "UPDATE prospect_replies SET approval_status = 'rejected' WHERE id = ?",
        (reply_id,),
    )
    conn.commit()
    conn.close()


def mark_reply_sent(reply_id: int):
    """Marque une réponse comme envoyée."""
    conn = get_conn()
    conn.execute(
        "UPDATE prospect_replies SET approval_status = 'sent', sent_at = datetime('now') WHERE id = ?",
        (reply_id,),
    )
    conn.commit()
    conn.close()


def update_draft_response(reply_id: int, new_draft: str):
    """Met à jour le brouillon de réponse (après édition manuelle)."""
    conn = get_conn()
    conn.execute(
        "UPDATE prospect_replies SET draft_response = ?, approval_status = 'pending' WHERE id = ?",
        (new_draft, reply_id),
    )
    conn.commit()
    conn.close()


def get_pending_replies() -> list[dict]:
    """Récupère toutes les réponses en attente d'approbation."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT r.*, p.name as prospect_name, p.company, p.role, p.industry,
               p.linkedin_headline, p.pain_points, p.personalization_brief
        FROM prospect_replies r
        JOIN prospects p ON r.prospect_id = p.id
        WHERE r.approval_status = 'pending'
        ORDER BY r.detected_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_replies(status_filter: Optional[str] = None) -> list[dict]:
    """Récupère toutes les réponses, optionnellement filtrées."""
    conn = get_conn()
    query = """
        SELECT r.*, p.name as prospect_name, p.company, p.role, p.industry
        FROM prospect_replies r
        JOIN prospects p ON r.prospect_id = p.id
    """
    params = []
    if status_filter and status_filter != "all":
        query += " WHERE r.approval_status = ?"
        params.append(status_filter)
    query += " ORDER BY r.detected_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
