"""Page 4 : Réglages."""

import os
import streamlit as st
from pathlib import Path
from core.db import init_db
from core.config import load_config
from core.auth import get_usage, is_admin

st.set_page_config(page_title="Réglages", page_icon="⚙️", layout="wide")

if not st.session_state.get("logged_in"):
    st.warning("Veuillez vous connecter depuis la page d'accueil.")
    st.stop()

init_db()
st.title("⚙️ Réglages")

client_id = st.session_state.get("client_id", "")

# ==========================================
# Quota du mois
# ==========================================
if not is_admin(client_id):
    usage = get_usage(client_id)
    st.markdown("### 📊 Votre utilisation ce mois")

    col1, col2 = st.columns(2)
    with col1:
        pct_p = int(usage["prospects"] / max(usage["quota_prospects"], 1) * 100)
        st.metric("Prospects trouvés", f"{usage['prospects']} / {usage['quota_prospects']}")
        st.progress(min(pct_p, 100) / 100)
    with col2:
        pct_m = int(usage["messages"] / max(usage["quota_messages"], 1) * 100)
        st.metric("Messages IA générés", f"{usage['messages']} / {usage['quota_messages']}")
        st.progress(min(pct_m, 100) / 100)

    st.markdown("---")

# ==========================================
# Votre offre
# ==========================================
st.markdown("### ✏️ Votre offre")
st.markdown("L'IA utilise ces infos pour personnaliser les messages de prospection.")

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env():
    values = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def save_env(values):
    lines = [f'{k}="{v}"' for k, v in values.items() if v]
    ENV_PATH.write_text("\n".join(lines) + "\n")


env = load_env()
cfg = load_config()

coach_product = st.text_input(
    "Qu'est-ce que vous vendez ?",
    value=env.get("COACH_PRODUCT", cfg.coach_product),
    placeholder="Ex: Coaching de leadership",
)
coach_icp = st.text_input(
    "À qui ?",
    value=env.get("COACH_ICP", cfg.coach_icp),
    placeholder="Ex: Dirigeants de PME",
)
coach_value_prop = st.text_area(
    "Pourquoi devraient-ils s'intéresser ?",
    value=env.get("COACH_VALUE_PROP", cfg.coach_value_prop),
    height=80,
    placeholder="Ex: Décrochez 5 à 15 RDV par mois sans y passer 2h/jour",
)

st.markdown("---")

# ==========================================
# Email (optionnel)
# ==========================================
st.markdown("### 📧 Email (optionnel)")
st.markdown("Pour envoyer les emails automatiquement. Sinon, copiez-collez les messages.")

show_email = st.toggle("Configurer l'envoi d'emails")

smtp_host = env.get("SMTP_HOST", "smtp.gmail.com")
smtp_port = env.get("SMTP_PORT", "587")
smtp_user = env.get("SMTP_USER", "")
smtp_password = env.get("SMTP_PASSWORD", "")
smtp_sender = env.get("SMTP_SENDER_NAME", "")
imap_host = env.get("IMAP_HOST", "imap.gmail.com")
imap_port = env.get("IMAP_PORT", "993")
imap_user = env.get("IMAP_USER", "")
imap_password = env.get("IMAP_PASSWORD", "")

if show_email:
    st.markdown("**Envoi**")
    col1, col2 = st.columns(2)
    with col1:
        smtp_user = st.text_input("Votre email", value=smtp_user, placeholder="vous@gmail.com")
        smtp_sender = st.text_input("Votre nom", value=smtp_sender, placeholder="Marie Dupont")
    with col2:
        smtp_password = st.text_input("Mot de passe d'application Gmail", value=smtp_password, type="password")
        smtp_host = st.text_input("Serveur SMTP", value=smtp_host)

    st.markdown("**Réception des réponses**")
    col3, col4 = st.columns(2)
    with col3:
        imap_user = st.text_input("Email de réception", value=imap_user, placeholder="vous@gmail.com")
    with col4:
        imap_password = st.text_input("Mot de passe IMAP", value=imap_password, type="password")

st.markdown("---")

# ==========================================
# Sauvegarder
# ==========================================
if st.button("💾 Sauvegarder", type="primary"):
    save_env({
        "COACH_PRODUCT": coach_product,
        "COACH_ICP": coach_icp,
        "COACH_VALUE_PROP": coach_value_prop,
        "SMTP_HOST": smtp_host,
        "SMTP_PORT": smtp_port,
        "SMTP_USER": smtp_user,
        "SMTP_PASSWORD": smtp_password,
        "SMTP_SENDER_NAME": smtp_sender,
        "IMAP_HOST": imap_host,
        "IMAP_PORT": imap_port,
        "IMAP_USER": imap_user,
        "IMAP_PASSWORD": imap_password,
    })
    st.success("✅ Sauvegardé !")
