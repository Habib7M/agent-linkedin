"""Page 2 : Lancer la campagne."""

import streamlit as st
from core.db import init_db, get_eligible_prospects, get_total_prospects
from core.campaign_runner import run_campaign
from core.config import load_config

st.set_page_config(page_title="Campagne", page_icon="🚀", layout="wide")

if not st.session_state.get("logged_in"):
    st.warning("Veuillez vous connecter depuis la page d'accueil.")
    st.stop()

init_db()
st.title("🚀 Lancer la campagne")
st.caption("L'IA analyse chaque prospect et écrit un message personnalisé.")
st.markdown("---")

cfg = load_config()
from core.auth import check_quota, get_usage

client_id = st.session_state.get("client_id", "")

# Vérifier le quota
if not check_quota(client_id, "messages"):
    usage = get_usage(client_id)
    st.error(f"Quota mensuel atteint ({usage['messages']}/{usage['quota_messages']} messages). Contactez l'administrateur.")
    st.stop()

total = get_total_prospects()
if total == 0:
    st.error("Aucun prospect dans votre liste. Allez dans **🔍 Prospects** d'abord.")
    st.stop()

# Stats
eligible = get_eligible_prospects(cfg.min_score)
n = len(eligible)

st.metric("Prospects prêts à contacter", n)
st.markdown("")

# Séquence expliquée
st.markdown("### Ce qui va se passer")
st.markdown(
    f"L'IA va écrire un message personnalisé pour chacun de vos **{n} prospects**.\n\n"
    "La séquence automatique :\n"
    "1. **Jour 0** — Message LinkedIn\n"
    "2. **Jour 3** — Email\n"
    "3. **Jour 7** — Relance LinkedIn\n"
    "4. **Jour 14** — Dernier email"
)

st.markdown("---")

# Mode test
dry_run = st.toggle("🧪 Mode test — voir les messages sans les envoyer", value=True)

if dry_run:
    st.info("Aucun message ne sera envoyé. Vous pourrez les relire avant de décider.")
else:
    st.warning("Les emails seront envoyés pour de vrai. Vérifiez vos réglages email.")

st.markdown("---")

# Bouton
if n == 0:
    st.error("Aucun prospect éligible.")
    st.stop()

launch = False
if st.button(f"▶ Lancer ({n} prospects)", type="primary"):
    if not dry_run:
        if st.checkbox("Je confirme vouloir envoyer pour de vrai"):
            launch = True
    else:
        launch = True

if launch:
    st.markdown("---")
    bar = st.progress(0)
    status = st.empty()

    def on_progress(current, total_count, msg):
        bar.progress(current / total_count)
        status.text(msg)

    with st.spinner("L'IA rédige les messages..."):
        stats = run_campaign(
            min_score=cfg.min_score,
            rate_limit=cfg.rate_limit_per_hour,
            dry_run=dry_run,
            progress_callback=on_progress,
        )

    bar.progress(1.0)
    status.empty()

    st.success(f"✅ Terminé — {stats['sent']} messages créés !")

    if stats.get("failed"):
        st.warning(f"{stats['failed']} ont échoué")

    # Afficher les messages
    if stats.get("messages"):
        st.markdown("### Messages générés")
        for msg in stats["messages"]:
            with st.expander(f"💬 {msg['prospect_name']}"):
                if msg.get("subject"):
                    st.markdown(f"**Objet :** {msg['subject']}")
                st.text(msg["body"])
