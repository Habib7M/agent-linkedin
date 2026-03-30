"""Scoring et priorisation des prospects — inclut bonus profil enrichi."""

import re
from .db import get_conn

# 🔧 CUSTOMIZE: mots-clés pour détecter les rôles cibles (coachs de vie)
DECISION_MAKER_KEYWORDS = [
    "coach", "coaching", "fondateur", "fondatrice", "gérant", "gérante",
    "indépendant", "indépendante", "praticien", "praticienne",
    "thérapeute", "sophrologue", "formateur", "formatrice",
    "consultant", "consultante", "accompagnateur", "accompagnatrice",
    "mentor", "facilitateur", "facilitatrice",
]

# 🔧 CUSTOMIZE: secteurs alignés avec l'ICP (coachs de vie)
ALIGNED_INDUSTRIES = [
    "coaching", "développement personnel", "bien-être", "wellness",
    "formation", "accompagnement", "thérapie", "sophrologie",
    "parentalité", "famille", "sport", "entreprise", "leadership",
    "reconversion", "transition", "santé", "holistique",
]

# Champs de profil qui comptent pour le bonus enrichissement
PROFILE_FIELDS = [
    "linkedin_headline", "linkedin_about", "recent_activity",
    "skills", "experience_summary", "pain_points", "mutual_context",
]


def score_prospect(prospect: dict) -> int:
    """Calcule le score d'un prospect (0-100).

    Base (max 80) :
      +20 email valide
      +15 LinkedIn URL
      +25 rôle décideur
      +20 secteur aligné ICP

    Signaux (max 20) :
      +10 custom_signal présent
      +10 profil enrichi (≥3 champs de profil remplis)

    Un profil enrichi permet une meilleure personnalisation, donc un meilleur taux de réponse.
    """
    score = 0

    # Email valide
    email = prospect.get("email", "") or ""
    if email and re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        score += 20

    # LinkedIn
    linkedin = prospect.get("linkedin_url", "") or ""
    if linkedin and "linkedin.com" in linkedin.lower():
        score += 15

    # Rôle décideur — chercher dans role, headline ET about
    role = (prospect.get("role", "") or "").lower()
    headline = (prospect.get("linkedin_headline", "") or "").lower()
    about = (prospect.get("linkedin_about", "") or "").lower()
    all_text = f"{role} {headline} {about}"
    if any(kw in all_text for kw in DECISION_MAKER_KEYWORDS):
        score += 25

    # Secteur aligné — chercher aussi dans role/headline/about
    industry = (prospect.get("industry", "") or "").lower()
    all_industry = f"{industry} {all_text}"
    if any(kw in all_industry for kw in ALIGNED_INDUSTRIES):
        score += 20

    # Custom signal
    signal = prospect.get("custom_signal", "") or ""
    if signal.strip():
        score += 10

    # Bonus profil enrichi — plus de champs = meilleure personnalisation
    filled_profile_fields = sum(
        1 for f in PROFILE_FIELDS
        if (prospect.get(f, "") or "").strip()
    )
    if filled_profile_fields >= 3:
        score += 10

    return min(score, 100)


def score_all_prospects():
    """Score tous les prospects en DB et met à jour leur statut."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM prospects").fetchall()
    for row in rows:
        p = dict(row)
        s = score_prospect(p)
        new_status = "scored" if p["status"] in ("new", "enriched") else p["status"]
        conn.execute(
            "UPDATE prospects SET score = ?, status = ? WHERE id = ?",
            (s, new_status, p["id"])
        )
    conn.commit()
    conn.close()
