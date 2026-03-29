"""Dataclasses métier : Prospect, SendResult."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum
import uuid


class ProspectStatus(Enum):
    NEW = "new"
    ENRICHED = "enriched"
    SCORED = "scored"
    CONTACTED = "contacted"
    REPLIED = "replied"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"
    MEETING_BOOKED = "meeting_booked"
    NOT_INTERESTED = "not_interested"


class Channel(Enum):
    EMAIL = "email"
    LINKEDIN = "linkedin"
    BOTH = "both"


@dataclass
class Prospect:
    name: str
    company: str
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    role: Optional[str] = None
    company_size: Optional[str] = None
    industry: Optional[str] = None
    custom_signal: Optional[str] = None

    # --- Champs de profil enrichis pour personnalisation ---
    linkedin_headline: Optional[str] = None       # Titre LinkedIn ("Coach | Conférencier | ...")
    linkedin_about: Optional[str] = None           # Section "À propos" LinkedIn
    recent_activity: Optional[str] = None          # Posts/articles récents, commentaires notables
    skills: Optional[str] = None                   # Compétences clés listées
    experience_summary: Optional[str] = None       # Parcours résumé (ex: "10 ans en finance, puis pivot RH")
    pain_points: Optional[str] = None              # Points de douleur identifiés (rempli manuellement ou via analyse)
    mutual_context: Optional[str] = None           # Connexions mutuelles, groupes communs, événements partagés
    tone_preference: Optional[str] = None          # "formel", "décontracté", "pair-à-pair" — déduit ou choisi
    # 🔧 CUSTOMIZE: ajouter d'autres champs selon votre niche

    status: ProspectStatus = ProspectStatus.NEW
    score: int = 0
    current_step: int = 0
    ab_variant: Optional[str] = None
    last_contacted_at: Optional[datetime] = None
    channel: Channel = Channel.EMAIL
    personalization_brief: Optional[str] = None    # Brief généré par le profile_analyzer
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)


# Champs CSV reconnus à l'import
PROFILE_CSV_FIELDS = [
    "linkedin_headline", "linkedin_about", "recent_activity",
    "skills", "experience_summary", "pain_points",
    "mutual_context", "tone_preference",
]


@dataclass
class SendResult:
    prospect_id: str
    channel: str
    step: int
    status: str  # "sent" | "failed" | "bounced" | "rate_limited"
    message_subject: str  # Sujet (email) ou "" (LinkedIn)
    message_preview: str  # Premiers 100 chars
    error: Optional[str] = None
    ab_variant: Optional[str] = None
    sent_at: datetime = field(default_factory=datetime.utcnow)
