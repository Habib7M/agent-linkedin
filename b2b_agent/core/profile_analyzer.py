"""Analyse de profil prospect — extrait des accroches de personnalisation.

1. build_profile_context() : agrège toutes les infos du prospect
2. generate_personalization_brief() : appelle l'IA pour créer un brief de personnalisation
"""

from .config import load_config
from .db import update_personalization_brief
from .llm import appeler_ia


def build_profile_context(prospect: dict) -> str:
    """Agrège toutes les données du prospect en un bloc structuré."""
    sections = []

    identity_parts = []
    if prospect.get("name"):
        identity_parts.append(f"Nom : {prospect['name']}")
    if prospect.get("role"):
        identity_parts.append(f"Poste : {prospect['role']}")
    if prospect.get("company"):
        identity_parts.append(f"Entreprise : {prospect['company']}")
    if prospect.get("company_size"):
        identity_parts.append(f"Taille : {prospect['company_size']}")
    if prospect.get("industry"):
        identity_parts.append(f"Secteur : {prospect['industry']}")
    if identity_parts:
        sections.append("IDENTITÉ :\n" + "\n".join(f"  - {p}" for p in identity_parts))

    linkedin_parts = []
    if prospect.get("linkedin_headline"):
        linkedin_parts.append(f"Headline : {prospect['linkedin_headline']}")
    if prospect.get("linkedin_about"):
        linkedin_parts.append(f"À propos : {prospect['linkedin_about']}")
    if prospect.get("skills"):
        linkedin_parts.append(f"Compétences : {prospect['skills']}")
    if prospect.get("experience_summary"):
        linkedin_parts.append(f"Parcours : {prospect['experience_summary']}")
    if linkedin_parts:
        sections.append("PROFIL LINKEDIN :\n" + "\n".join(f"  - {p}" for p in linkedin_parts))

    signal_parts = []
    if prospect.get("custom_signal"):
        signal_parts.append(f"Signal détecté : {prospect['custom_signal']}")
    if prospect.get("recent_activity"):
        signal_parts.append(f"Activité récente : {prospect['recent_activity']}")
    if prospect.get("mutual_context"):
        signal_parts.append(f"Contexte commun : {prospect['mutual_context']}")
    if signal_parts:
        sections.append("SIGNAUX :\n" + "\n".join(f"  - {p}" for p in signal_parts))

    if prospect.get("pain_points"):
        sections.append(f"POINTS DE DOULEUR IDENTIFIÉS :\n  - {prospect['pain_points']}")

    if prospect.get("tone_preference"):
        sections.append(f"TON SUGGÉRÉ : {prospect['tone_preference']}")

    return "\n\n".join(sections) if sections else f"Nom : {prospect.get('name', '?')}, Entreprise : {prospect.get('company', '?')}"


def generate_personalization_brief(prospect: dict, force: bool = False) -> str:
    """Génère et stocke un brief de personnalisation pour un prospect."""
    if not force and prospect.get("personalization_brief"):
        return prospect["personalization_brief"]

    cfg = load_config()
    profile_context = build_profile_context(prospect)

    system_prompt = (
        "Tu es un expert en prospection B2B et en psychologie professionnelle. "
        "Tu analyses des profils pour trouver LE bon angle d'approche. "
        "Tu es concret et spécifique — jamais de phrases passe-partout."
    )

    user_prompt = f"""Analyse ce profil et produis un BRIEF DE PERSONNALISATION pour rédiger un message de prospection.

--- PROFIL DU PROSPECT ---
{profile_context}
--- FIN PROFIL ---

--- CONTEXTE (celui qui prospecte) ---
Produit : {cfg.coach_product}
Client idéal : {cfg.coach_icp}
Proposition de valeur : {cfg.coach_value_prop}
--- FIN CONTEXTE ---

Produis un brief avec EXACTEMENT ces 5 sections. Sois SPÉCIFIQUE à ce profil — pas de phrases génériques.

ACCROCHE_PROFIL: Un fait CONCRET tiré du profil (headline, poste, parcours, compétence) qui peut servir d'ouverture. PAS "j'ai vu votre profil". Cite le fait précis.

PONT_PERTINENCE: Le lien LOGIQUE entre la situation de cette personne et l'offre. Explique POURQUOI cette offre a du sens pour ELLE spécifiquement.

SIGNAL_EXPLOITABLE: L'élément le plus fort du profil (changement de poste, nouveau rôle, croissance, spécialisation) et comment l'intégrer dans le message. Si aucun signal fort : dire "Aucun signal fort — utiliser le rôle et le secteur".

POINT_DOULEUR_PROBABLE: Le défi ou la frustration la plus probable VU le profil et le poste. Être réaliste, pas inventer.

TON_RECOMMANDÉ: Le registre (formel/décontracté, pair-à-pair/expert) et POURQUOI ce ton convient à ce profil.

Écris en français. Chaque section = 1-2 phrases max, concrètes.
"""

    brief = appeler_ia(system_prompt, user_prompt, temperature=0.6, max_tokens=600)

    if prospect.get("id"):
        update_personalization_brief(prospect["id"], brief)

    return brief


def parse_brief_section(brief: str, section: str) -> str:
    """Extrait une section spécifique du brief."""
    lines = brief.split("\n")
    capture = False
    result = []

    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith(section.upper()):
            capture = True
            after_colon = stripped.split(":", 1)
            if len(after_colon) > 1 and after_colon[1].strip():
                result.append(after_colon[1].strip())
            continue

        if capture and stripped and any(
            stripped.upper().startswith(s)
            for s in ["ACCROCHE_PROFIL", "PONT_PERTINENCE", "SIGNAL_EXPLOITABLE",
                       "POINT_DOULEUR_PROBABLE", "TON_RECOMMANDÉ"]
            if s != section.upper()
        ):
            break

        if capture and stripped:
            result.append(stripped)

    return " ".join(result)
