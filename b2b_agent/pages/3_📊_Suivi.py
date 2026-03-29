"""Page 3 : Suivi des résultats + réponses."""

import streamlit as st
import pandas as pd
from core.db import (
    init_db, get_all_prospects, get_send_results,
    get_pending_replies, get_all_replies,
    approve_reply, reject_reply, mark_reply_sent,
    update_draft_response, get_prospect_by_id,
)
from core.metrics import get_campaign_metrics
from core.reply_generator import generate_aca_reply
from core.email_sender import send_email
from core.response_tracker import check_replies

st.set_page_config(page_title="Suivi", page_icon="📊", layout="wide")

if not st.session_state.get("logged_in"):
    st.warning("Veuillez vous connecter depuis la page d'accueil.")
    st.stop()

init_db()
st.title("📊 Résultats")
st.caption("Suivez vos campagnes et gérez les réponses.")
st.markdown("---")

# KPIs
metrics = get_campaign_metrics()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Envoyés", metrics["sent"])
col2.metric("Réponses", metrics["replied"])
col3.metric("Taux de réponse", f"{metrics['reply_rate']}%")
col4.metric("RDV décrochés", metrics["meetings"])

# Alerte réponses
pending = get_pending_replies()
if pending:
    st.markdown("---")
    st.warning(f"📬 **{len(pending)} réponse(s) à traiter** — voir ci-dessous")

st.markdown("---")

# ==========================================
# Réponses en attente
# ==========================================
st.markdown("### Réponses reçues")

if st.button("🔍 Vérifier s'il y a de nouvelles réponses"):
    with st.spinner("Vérification..."):
        new = check_replies(since_hours=6, auto_draft=True)
    if new:
        st.success(f"{len(new)} nouvelle(s) réponse(s) !")
        st.rerun()
    else:
        st.info("Aucune nouvelle réponse.")

st.markdown("")

if not pending:
    st.info("Aucune réponse en attente.")
else:
    for reply in pending:
        with st.container(border=True):
            st.markdown(f"#### {reply['prospect_name']}")

            # Ce que le prospect a dit
            st.markdown("**Il/elle a écrit :**")
            st.info(reply.get("body", "(message vide)"))

            # Brouillon de réponse
            draft = reply.get("draft_response", "")

            if not draft:
                if st.button("🤖 Générer une réponse", key=f"g_{reply['id']}"):
                    with st.spinner("L'IA écrit une réponse..."):
                        prospect = get_prospect_by_id(reply["prospect_id"])
                        result = generate_aca_reply(
                            prospect=prospect,
                            reply_subject=reply.get("subject", ""),
                            reply_body=reply.get("body", ""),
                        )
                        update_draft_response(reply["id"], f"Sujet: {result['subject']}\n\n{result['body']}")
                        st.rerun()
            else:
                st.markdown("**Réponse proposée par l'IA :**")
                edited = st.text_area("Vous pouvez modifier avant d'envoyer :", value=draft, height=150, key=f"d_{reply['id']}")

                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("✅ Envoyer", key=f"ok_{reply['id']}", type="primary"):
                        lines = (edited or draft).strip().split("\n")
                        subj = lines[0].split(":", 1)[1].strip() if lines[0].lower().startswith("sujet:") else ""
                        body = "\n".join(lines[1:]).strip() if subj else (edited or draft)

                        if reply.get("from_email"):
                            r = send_email(to_email=reply["from_email"], subject=subj, body=body, prospect_id=reply["prospect_id"], step=99)
                            if r.status == "sent":
                                mark_reply_sent(reply["id"])
                                st.success(f"✅ Réponse envoyée !")
                                st.rerun()
                            else:
                                st.error(f"Échec : {r.error}")
                        else:
                            approve_reply(reply["id"])
                            st.success("✅ Marqué comme traité")
                            st.rerun()
                with c2:
                    if st.button("🔄 Réécrire", key=f"re_{reply['id']}"):
                        with st.spinner("Réécriture..."):
                            prospect = get_prospect_by_id(reply["prospect_id"])
                            result = generate_aca_reply(prospect=prospect, reply_subject=reply.get("subject", ""), reply_body=reply.get("body", ""))
                            update_draft_response(reply["id"], f"Sujet: {result['subject']}\n\n{result['body']}")
                            st.rerun()
                with c3:
                    if st.button("❌ Ignorer", key=f"no_{reply['id']}"):
                        reject_reply(reply["id"])
                        st.rerun()

# ==========================================
# Liste des prospects
# ==========================================
st.markdown("---")
st.markdown("### Tous vos prospects")

search = st.text_input("Rechercher", placeholder="Nom ou entreprise...")

prospects = get_all_prospects()
if search:
    s = search.lower()
    prospects = [p for p in prospects if s in p.get("name", "").lower() or s in p.get("company", "").lower()]

if prospects:
    df = pd.DataFrame(prospects)
    cols = [c for c in ["name", "company", "role", "status", "score"] if c in df.columns]
    names = {"name": "Nom", "company": "Entreprise", "role": "Poste", "status": "Statut", "score": "Score"}
    df_show = df[cols].rename(columns=names).sort_values("Score", ascending=False)
    st.dataframe(df_show, use_container_width=True, height=400)

    # Export
    csv = df.to_csv(index=False)
    st.download_button("📥 Télécharger la liste complète", data=csv, file_name="mes_prospects.csv", mime="text/csv")
else:
    st.info("Aucun prospect.")
