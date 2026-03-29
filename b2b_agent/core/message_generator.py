"""Génération de messages — personnalisation profonde + validation."""

from pathlib import Path
from .config import load_config
from .llm import appeler_ia, appeler_ia_conversation
from .profile_analyzer import (
    generate_personalization_brief,
    build_profile_context,
    parse_brief_section,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _load_template(channel: str, step: str, variant: str = "a") -> str:
    """Charge un template depuis le dossier templates/."""
    if variant.lower() != "a":
        path = TEMPLATES_DIR / "variants" / f"{step}_{channel}_{variant.lower()}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
    path = TEMPLATES_DIR / f"{step}_{channel}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _build_system_prompt(cfg) -> str:
    """Construit le system prompt avec le contexte métier de la coach."""
    return f"""Tu es un rédacteur expert en prospection B2B personnalisée pour un coach professionnel.

CONTEXTE DU COACH :
- Produit/Service : {cfg.coach_product}
- Client idéal : {cfg.coach_icp}
- Proposition de valeur : {cfg.coach_value_prop}

TON OBJECTIF : écrire un message qui donne au prospect l'impression qu'on l'a vraiment compris — pas un message template avec son nom collé dessus.

PRINCIPES DE PERSONNALISATION :
1. L'OUVERTURE doit référencer un élément concret du profil (headline, parcours, activité récente, compétence). Jamais "j'ai vu votre profil".
2. Le PONT doit être logique : pourquoi cette offre fait sens pour CETTE personne dans SA situation.
3. Le SIGNAL doit être exploité naturellement — pas "j'ai vu que vous avez été promu" mais tisser cette info dans le fil du message.
4. Le CTA doit être une question ouverte ou une proposition d'échange, jamais une vente directe.

RÈGLES STRICTES :
- Ton empathique, pair-à-pair, orienté transformation. PAS commercial agressif.
- INTERDICTION absolue : "j'espère que vous allez bien", "je me permets de", "suite à", "n'hésitez pas", "j'ai vu votre profil", "je me suis permis de regarder"
- Email : < 150 mots, sujet inclus sur la première ligne au format "Sujet: ..."
- LinkedIn : < 300 caractères, pas de sujet
- Tutoiement interdit sauf indication contraire
- Pas de bullet points dans le corps du message
- Le message doit sembler écrit par un humain qui a pris 5 minutes pour comprendre le prospect
"""


def _build_personalized_prompt(
    prospect: dict,
    channel: str,
    step: str,
    template: str,
    brief: str,
    profile_context: str,
) -> str:
    """Construit le user prompt avec toutes les données de personnalisation."""

    # Extraire les sections du brief pour guider la génération
    accroche = parse_brief_section(brief, "ACCROCHE_PROFIL")
    pont = parse_brief_section(brief, "PONT_PERTINENCE")
    signal = parse_brief_section(brief, "SIGNAL_EXPLOITABLE")
    douleur = parse_brief_section(brief, "POINT_DOULEUR_PROBABLE")
    ton = parse_brief_section(brief, "TON_RECOMMANDÉ")

    step_instructions = {
        "cold": "C'est le PREMIER contact. Le prospect ne te connaît pas. L'objectif est d'éveiller la curiosité sans vendre.",
        "followup_1": "C'est un FOLLOW-UP après un premier message sans réponse. Change d'angle, apporte de la valeur (insight, cas concret, question).",
        "followup_2": "C'est le DEUXIÈME follow-up. Sois bref. Apporte un élément nouveau (article, témoignage, chiffre).",
        "breakup": "C'est le DERNIER message. Sois respectueux, laisse la porte ouverte. Pas de culpabilisation.",
        "followup": "C'est un FOLLOW-UP LinkedIn. Très court, apporte un élément de valeur.",
    }

    return f"""Génère un message de prospection {channel} (étape : {step}).

--- TEMPLATE (structure à suivre, PAS à copier mot pour mot) ---
{template}
--- FIN TEMPLATE ---

--- PROFIL COMPLET DU PROSPECT ---
{profile_context}
--- FIN PROFIL ---

--- BRIEF DE PERSONNALISATION (pré-analysé) ---
Accroche suggérée : {accroche or 'À créer à partir du profil'}
Pont de pertinence : {pont or 'À créer'}
Signal exploitable : {signal or 'Aucun signal fort — utiliser le rôle/secteur'}
Point de douleur probable : {douleur or 'À déduire du profil'}
Ton recommandé : {ton or 'Pair-à-pair, professionnel'}
--- FIN BRIEF ---

INSTRUCTION ÉTAPE : {step_instructions.get(step, '')}

CONSIGNES :
- Utilise le brief comme guide mais formule avec tes propres mots
- L'accroche doit être SPÉCIFIQUE à ce prospect (pas "j'ai vu votre profil LinkedIn")
- Le lien avec l'offre du coach doit être NATUREL, pas forcé
- {"Le message DOIT commencer par 'Sujet: ...' avec un objet personnalisé." if channel == "email" else "Pas de sujet, message < 300 caractères."}
- Si le brief mentionne un signal fort, intègre-le naturellement
- Adapte le registre au ton recommandé
"""


def _validate_message(text: str, channel: str, prospect: dict) -> list[str]:
    """Valide un message généré. Retourne la liste des problèmes."""
    issues = []

    if channel == "email":
        lines = text.strip().split("\n")
        if not lines[0].lower().startswith("sujet:"):
            issues.append("Pas de ligne 'Sujet:' en début de message email")
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""
        if len(body.split()) > 160:
            issues.append(f"Email trop long ({len(body.split())} mots, max 150)")
    elif channel == "linkedin":
        if len(text) > 300:
            issues.append(f"LinkedIn trop long ({len(text)} chars, max 300)")

    # Vérifier mentions spécifiques au prospect
    name = prospect.get("name", "")
    company = prospect.get("company", "")
    if name and name.lower() not in text.lower() and company.lower() not in text.lower():
        issues.append("Aucune mention du nom ou de l'entreprise du prospect")

    # Placeholders non résolus
    if "{" in text and "}" in text:
        issues.append("Placeholders non résolus détectés")

    # Phrases interdites
    banned = [
        "j'espère que vous allez bien", "je me permets", "n'hésitez pas",
        "j'ai vu votre profil", "je me suis permis de regarder",
    ]
    for phrase in banned:
        if phrase in text.lower():
            issues.append(f"Phrase interdite détectée : '{phrase}'")

    return issues


def generate_message(
    prospect: dict,
    channel: str,
    step: str,
    variant: str = "a",
    dry_run: bool = False,
) -> dict:
    """Génère un message hyper-personnalisé pour un prospect.

    Pipeline :
    1. Construit le contexte profil complet
    2. Récupère ou génère le brief de personnalisation (1 appel OpenAI, stocké en DB)
    3. Génère le message final en injectant brief + template + profil
    4. Valide et re-génère si nécessaire

    Args:
        prospect: dict avec toutes les infos du prospect
        channel: "email" ou "linkedin"
        step: "cold", "followup_1", "followup_2", "breakup", "followup"
        variant: "a" ou "b" pour A/B testing
        dry_run: si True, retourne le brief sans appeler l'API pour le message

    Returns:
        dict avec "subject", "body", "raw", "issues", "brief"
    """
    cfg = load_config()
    template = _load_template(channel, step, variant)
    profile_context = build_profile_context(prospect)

    # Étape 1 : générer ou récupérer le brief de personnalisation
    brief = generate_personalization_brief(prospect)

    # Étape 2 : générer le message personnalisé
    system_prompt = _build_system_prompt(cfg)
    user_prompt = _build_personalized_prompt(
        prospect, channel, step, template, brief, profile_context
    )

    text = appeler_ia(system_prompt, user_prompt, temperature=0.7, max_tokens=500)

    # Étape 3 : validation
    issues = _validate_message(text, channel, prospect)

    # Re-gen si problèmes (1 tentative)
    if issues:
        fix_prompt = (
            f"Le message précédent avait ces problèmes : {', '.join(issues)}. "
            f"Corrige et régénère en gardant la personnalisation du profil.\n\n"
            f"Message précédent :\n{text}"
        )
        try:
            text = appeler_ia_conversation(
                system_prompt,
                [
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": fix_prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )
            issues = _validate_message(text, channel, prospect)
        except Exception:
            pass

    # Parser sujet / body pour email
    subject = ""
    body = text
    if channel == "email":
        lines = text.strip().split("\n")
        if lines[0].lower().startswith("sujet:"):
            subject = lines[0].split(":", 1)[1].strip()
            body = "\n".join(lines[1:]).strip()

    return {
        "subject": subject,
        "body": body,
        "raw": text,
        "issues": issues,
        "brief": brief,
    }


def save_template(channel: str, step: str, variant: str, content: str):
    """Sauvegarde un template dans le dossier templates/."""
    if variant.lower() != "a":
        path = TEMPLATES_DIR / "variants" / f"{step}_{channel}_{variant.lower()}.txt"
    else:
        path = TEMPLATES_DIR / f"{step}_{channel}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_template_content(channel: str, step: str, variant: str = "a") -> str:
    """Charge le contenu d'un template (pour l'éditeur UI)."""
    return _load_template(channel, step, variant)
