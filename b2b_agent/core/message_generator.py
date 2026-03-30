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
    return f"""Tu écris des messages de prospection pour un professionnel. Tu écris comme un HUMAIN, pas comme une IA.

QUI TU ES (le prospecteur) :
- Produit/Service : {cfg.coach_product}
- Client idéal : {cfg.coach_icp}
- Proposition de valeur : {cfg.coach_value_prop}

TA PHILOSOPHIE : Tu construis une RELATION avant de vendre quoi que ce soit. C'est comme dans la vraie vie : on ne demande pas à quelqu'un comment il gère son business 30 secondes après l'avoir rencontré. D'abord on se connecte, on montre un intérêt sincère, et c'est seulement après qu'on parle business.

LA PROGRESSION NATURELLE :
1. PREMIER MESSAGE (LinkedIn) : Juste nouer le lien. Un petit compliment sincère ou un point commun. Proposer de se connecter. C'est TOUT. Pas de question business.
2. RELANCE (après connexion) : Maintenant qu'on est connectés, on peut poser une question légère sur leur activité.
3. EMAIL : Là on peut parler un peu plus, mentionner ce qu'on fait, proposer un échange.
4. DERNIER MESSAGE : Court, respectueux, porte ouverte.

EXEMPLES PREMIER CONTACT LINKEDIN :

✅ BON :
"Bonjour Nathalie, je m'intéresse beaucoup au coaching de vie et votre profil a retenu mon attention. Au plaisir d'échanger !"

✅ BON :
"Bonjour Marc, votre approche du coaching m'a l'air passionnante. Je serais curieux d'en savoir plus, au plaisir de se connecter."

✅ BON :
"Bonjour Sophie, je travaille aussi dans l'univers du coaching et votre profil m'a parlé. Ravie de vous ajouter à mon réseau !"

❌ TROP INTRUSIF (question business dès le premier message) :
"Bonjour Nathalie, comment trouvez-vous vos clients aujourd'hui ?"

❌ TROP EN FAIRE :
"Votre travail chez Perspectives 66 sur l'autonomie des clients m'a interpellée, c'est rare de voir un coach aligner sa pratique avec cette valeur."

❌ TROP GÉNÉRIQUE :
"Bonjour, j'ai vu votre profil et je pense que notre solution pourrait vous intéresser."

EXEMPLES EMAIL (plus tard dans la séquence) :

✅ BON :
"Sujet: Question rapide

Bonjour Patricia,

Je travaille avec des coachs de vie pour les aider à trouver plus de clients via LinkedIn. En regardant votre profil, je me suis dit que le sujet pourrait vous parler.

Est-ce que la prospection client est un sujet pour vous en ce moment ?

Bonne journée,"

RÈGLES STRICTES :
- Ton décontracté mais respectueux. Comme un message qu'on enverrait vraiment à quelqu'un qu'on ne connaît pas.
- Email : < 100 mots, sujet court et simple sur la première ligne "Sujet: ..."
- LinkedIn : < 250 caractères. Court. Simple. Pas de pavé.
- Vouvoiement par défaut
- PAS de tirets (ni —, ni –). Utilise des virgules ou des points.
- PAS de bullet points, de gras, d'émojis
- PAS de phrases sophistiquées ou littéraires. Écris simple, comme on parle.
- ACCORD DU GENRE : accorde au féminin si le prénom est féminin (interpellée, intriguée, tombée, etc.)
- PHRASES INTERDITES : "j'espère que vous allez bien", "je me permets de", "n'hésitez pas", "j'ai vu votre profil", "je me suis permis", "je serais ravi de", "dans le cadre de", "solutions adaptées", "synergie", "optimiser", "je vous contacte car", "permettez-moi de me présenter", "votre expertise", "votre parcours remarquable", "c'est rare de voir"
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
        "cold": "PREMIER CONTACT. Commence par 'Bonjour {prénom},'. Le but est UNIQUEMENT de nouer le lien. Un compliment sincère sur leur profil ou un point commun + proposer de se connecter. PAS de question business, PAS d'offre. Juste être sympa et humain. 2 phrases max.",
        "followup_1": "PREMIER EMAIL. On peut maintenant parler un peu plus. Mentionne ce que tu fais en 1 phrase, fais le lien avec leur activité, pose UNE question légère. Reste décontracté.",
        "followup_2": "DEUXIÈME RELANCE. Court. Partage un résultat concret ou un chiffre utile. Propose un échange de 10 min.",
        "breakup": "DERNIER MESSAGE. 2-3 phrases. Respectueux. Pas de culpabilisation. La porte reste ouverte.",
        "followup": "RELANCE LinkedIn. Maintenant qu'on est connectés, pose une question légère sur leur activité. Pas de pitch. 2 phrases max.",
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
- Écris le message FINAL directement, prêt à envoyer. Pas de crochets, pas d'instructions.
- Utilise le brief comme guide mais formule avec tes propres mots
- L'accroche doit être SPÉCIFIQUE à ce prospect
- Le lien avec l'offre doit être NATUREL, pas forcé
- {"Le message DOIT commencer par 'Sujet: ...' avec un objet court et personnalisé. Corps < 120 mots." if channel == "email" else "Pas de sujet. Message COMPLET < 280 caractères. Pas de 'Bien à vous' ni formule de politesse."}
- Si le brief mentionne un signal fort, intègre-le naturellement
- Adapte le registre au ton recommandé
- NE PAS inclure de signature, ni [Votre nom], ni [Prénom]
"""


def _validate_message(text: str, channel: str, prospect: dict) -> list[str]:
    """Valide un message généré. Retourne la liste des problèmes."""
    issues = []

    if channel == "email":
        lines = text.strip().split("\n")
        if not lines[0].lower().startswith("sujet:"):
            issues.append("Pas de ligne 'Sujet:' en début de message email")
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""
        if len(body.split()) > 140:
            issues.append(f"Email trop long ({len(body.split())} mots, max 120)")
    elif channel == "linkedin":
        if len(text) > 300:
            issues.append(f"LinkedIn trop long ({len(text)} chars, max 280)")

    # Vérifier mentions spécifiques au prospect
    name = prospect.get("name", "")
    company = prospect.get("company", "")
    if name and name.lower() not in text.lower() and company.lower() not in text.lower():
        issues.append("Aucune mention du nom ou de l'entreprise du prospect")

    # Tirets cadratins (signature typique de l'IA)
    if "—" in text or "–" in text:
        issues.append("Tirets cadratins détectés (style IA)")

    # Placeholders non résolus
    if "{" in text and "}" in text:
        issues.append("Placeholders non résolus détectés")

    # Phrases interdites (spam B2B classique)
    banned = [
        "j'espère que vous allez bien",
        "je me permets",
        "n'hésitez pas",
        "j'ai vu votre profil",
        "je me suis permis de regarder",
        "je serais ravi",
        "je serais ravie",
        "dans le cadre de",
        "solutions adaptées",
        "permettez-moi de me présenter",
        "je vous contacte car",
        "je me présente",
        "synergie",
        "optimiser votre",
        "booster votre",
        "proposition de collaboration",
        "opportunité unique",
        "à votre disposition",
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
