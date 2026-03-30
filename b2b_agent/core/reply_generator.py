"""Génération de réponses aux prospects — Cadre A-C-A.

A-C-A = Acknowledge (accuser réception) → Connect (faire le lien) → Ask (proposer la suite)
Chaque réponse est un brouillon que l'utilisateur approuve avant envoi.
"""

from .config import load_config
from .llm import appeler_ia
from .profile_analyzer import build_profile_context, parse_brief_section


def _build_aca_system_prompt(cfg) -> str:
    return f"""Tu es un assistant de réponse pour un coach professionnel.

CONTEXTE DU COACH :
- Produit/Service : {cfg.coach_product}
- Client idéal : {cfg.coach_icp}
- Proposition de valeur : {cfg.coach_value_prop}

TU UTILISES LE CADRE A-C-A :

**A — ACKNOWLEDGE** : Montre que tu as lu et compris le message du prospect.
**C — CONNECT** : Relie ce qu'il a dit à une valeur concrète.
**A — ASK** : Pose UNE question ou propose UNE prochaine étape.

RÈGLES :
- Ton naturel, empathique. PAS commercial.
- < 100 mots
- Le cadre A-C-A est INVISIBLE dans le message final
- ACCORD DU GENRE : Détermine le genre à partir du PRÉNOM du prospect. Accorde au féminin si femme, masculin si homme.
- INTERDICTION : "merci pour votre réponse", "ravi de votre retour", "n'hésitez pas"
"""


def generate_aca_reply(prospect: dict, reply_subject: str, reply_body: str, dry_run: bool = False) -> dict:
    """Génère un brouillon de réponse avec le cadre A-C-A."""
    if dry_run:
        return {
            "subject": f"Re: {reply_subject}",
            "body": "[Mode test — réponse non générée]",
            "aca_breakdown": {"acknowledge": "", "connect": "", "ask": ""},
        }

    cfg = load_config()
    profile_context = build_profile_context(prospect)
    brief = prospect.get("personalization_brief", "")
    pont = parse_brief_section(brief, "PONT_PERTINENCE") if brief else ""
    douleur = parse_brief_section(brief, "POINT_DOULEUR_PROBABLE") if brief else ""

    user_prompt = f"""Un prospect a répondu. Génère une réponse avec le cadre A-C-A.

--- MESSAGE DU PROSPECT ---
Sujet : {reply_subject}
{reply_body}
--- FIN ---

--- PROFIL ---
{profile_context}
--- FIN ---

CONSIGNES :
1. Commence par "Sujet: Re: ..." sur la première ligne
2. < 100 mots, ton naturel
3. Après le message, ajoute :
---ACA---
A: [ce que tu reconnais]
C: [le lien que tu fais]
A: [ce que tu proposes]
---FIN ACA---
"""

    system_prompt = _build_aca_system_prompt(cfg)
    text = appeler_ia(system_prompt, user_prompt, temperature=0.7, max_tokens=400)

    # Parser
    subject, body = "", text
    lines = text.strip().split("\n")
    if lines[0].lower().startswith("sujet:"):
        subject = lines[0].split(":", 1)[1].strip()
        body = "\n".join(lines[1:]).strip()

    aca_breakdown = {"acknowledge": "", "connect": "", "ask": ""}
    if "---ACA---" in body:
        parts = body.split("---ACA---")
        body = parts[0].strip()
        if len(parts) > 1:
            aca_text = parts[1].replace("---FIN ACA---", "").strip()
            for line in aca_text.split("\n"):
                line = line.strip()
                if line.startswith("A:") and not aca_breakdown["acknowledge"]:
                    aca_breakdown["acknowledge"] = line[2:].strip()
                elif line.startswith("C:"):
                    aca_breakdown["connect"] = line[2:].strip()
                elif line.startswith("A:"):
                    aca_breakdown["ask"] = line[2:].strip()

    return {"subject": subject, "body": body, "aca_breakdown": aca_breakdown}
