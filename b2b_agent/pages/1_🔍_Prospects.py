"""Page 1 : Trouver et importer des prospects."""

import re
import uuid
import streamlit as st
import pandas as pd
from core.db import init_db, get_conn, upsert_prospect, get_total_prospects
from core.models import Prospect, Channel, PROFILE_CSV_FIELDS
from core.scorer import score_prospect, score_all_prospects
from core.prospect_finder import search_prospects, search_multiple_queries

st.set_page_config(page_title="Prospects", page_icon="🔍", layout="wide")

if not st.session_state.get("logged_in"):
    st.warning("Veuillez vous connecter depuis la page d'accueil.")
    st.stop()

init_db()
st.title("🔍 Trouver des prospects")
st.caption("Cherchez des profils LinkedIn ou importez votre propre liste.")
st.markdown("---")

# ==========================================
# Recherche automatique
# ==========================================
st.markdown("### Recherche automatique")
st.markdown("Tapez ce que vous cherchez et l'app trouve les profils LinkedIn pour vous.")
st.markdown("")

query = st.text_input(
    "Qui voulez-vous contacter ?",
    placeholder="Exemple : coach de vie Paris",
)

col1, col2 = st.columns([1, 3])
with col1:
    max_results = st.slider("Combien de résultats ?", 5, 30, 15)
with col2:
    st.markdown("")
    st.markdown("")
    search_clicked = st.button("🔍 Chercher", type="primary", disabled=not query)

if search_clicked:
    with st.spinner("Recherche en cours..."):
        try:
            results = search_prospects(query, max_results=max_results)
            if results:
                st.session_state["search_results"] = results
                st.success(f"✅ {len(results)} profils trouvés !")
            else:
                st.warning("Aucun résultat. Essayez d'autres mots-clés.")
                st.session_state["search_results"] = []
        except Exception as e:
            st.error(f"Erreur : {str(e)}")

# Résultats
if st.session_state.get("search_results"):
    results = st.session_state["search_results"]
    st.markdown("---")
    st.markdown(f"### {len(results)} profils trouvés")
    st.caption("Décochez ceux que vous ne voulez pas importer.")
    st.markdown("")

    selected = []
    for i, p in enumerate(results):
        cols = st.columns([0.3, 5])
        with cols[0]:
            if st.checkbox("", value=True, key=f"s_{i}"):
                selected.append(i)
        with cols[1]:
            name = p.get("name", "")
            headline = p.get("linkedin_headline", "")
            url = p.get("linkedin_url", "")
            st.markdown(f"**{name}** — {headline}")
            if url:
                st.caption(url)

    st.markdown("---")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(f"📥 Ajouter {len(selected)} prospects à ma liste", type="primary", disabled=not selected):
            conn = get_conn()
            added, already = 0, 0
            for idx in selected:
                p = results[idx]
                if conn.execute("SELECT id FROM prospects WHERE linkedin_url = ?", (p["linkedin_url"],)).fetchone():
                    already += 1
                    continue
                score = score_prospect(p)
                conn.execute(
                    """INSERT INTO prospects (id, name, company, email, linkedin_url, role, industry,
                    custom_signal, linkedin_headline, linkedin_about, recent_activity, skills,
                    experience_summary, pain_points, mutual_context, tone_preference, score, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4())[:8], p["name"], p.get("company", ""), p.get("email", ""),
                     p["linkedin_url"], p.get("role", ""), p.get("industry", ""),
                     p.get("custom_signal", ""), p.get("linkedin_headline", ""),
                     p.get("linkedin_about", ""), p.get("recent_activity", ""),
                     p.get("skills", ""), p.get("experience_summary", ""),
                     p.get("pain_points", ""), p.get("mutual_context", ""),
                     p.get("tone_preference", ""), score, "scored"))
                added += 1
            conn.commit()
            conn.close()
            if added:
                st.success(f"✅ {added} prospects ajoutés !")
            if already:
                st.info(f"{already} déjà dans votre liste")

    with col_b:
        if selected:
            csv_df = pd.DataFrame([results[i] for i in selected])
            st.download_button("📄 Télécharger en fichier", data=csv_df.drop(columns=["source"], errors="ignore").to_csv(index=False), file_name="prospects.csv", mime="text/csv")

# ==========================================
# Import fichier (optionnel)
# ==========================================
st.markdown("---")
with st.expander("📤 J'ai déjà une liste de contacts (fichier CSV)"):
    st.markdown("Si vous avez déjà une liste dans un tableur, déposez-la ici.")

    simple_csv = "name,company,email,linkedin_url,role\nJean Dupont,Acme,jean@acme.fr,https://linkedin.com/in/jean,Coach\n"
    st.download_button("📥 Voir le modèle de fichier", data=simple_csv, file_name="modele.csv", mime="text/csv")

    uploaded = st.file_uploader("Glissez votre fichier ici", type=["csv"])
    if uploaded:
        try:
            df = pd.read_csv(uploaded)
            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
            if "name" not in df.columns or "company" not in df.columns:
                st.error("Le fichier doit avoir au moins les colonnes 'name' et 'company'.")
            else:
                st.dataframe(df.head(5), use_container_width=True)
                valid = df.dropna(subset=["name", "company"])
                st.success(f"{len(valid)} contacts trouvés dans le fichier")

                if st.button("📥 Importer", type="primary"):
                    imported = 0
                    for _, row in valid.iterrows():
                        has_e = pd.notna(row.get("email", None))
                        has_l = pd.notna(row.get("linkedin_url", None))
                        channel = Channel.BOTH if (has_e and has_l) else (Channel.LINKEDIN if has_l else Channel.EMAIL)
                        def _g(c):
                            v = row.get(c, None)
                            return str(v).strip() if pd.notna(v) and str(v).strip() else None
                        try:
                            upsert_prospect(Prospect(
                                name=str(row["name"]).strip(), company=str(row["company"]).strip(),
                                email=str(row["email"]).strip() if has_e else None,
                                linkedin_url=str(row["linkedin_url"]).strip() if has_l else None,
                                role=_g("role"), industry=_g("industry"), custom_signal=_g("custom_signal"),
                                linkedin_headline=_g("linkedin_headline"), linkedin_about=_g("linkedin_about"),
                                channel=channel,
                            ))
                            imported += 1
                        except Exception:
                            pass
                    score_all_prospects()
                    st.success(f"✅ {imported} contacts importés !")
        except Exception as e:
            st.error(f"Erreur : {e}")

# Stats
st.markdown("---")
total = get_total_prospects()
if total > 0:
    st.metric("Total dans votre liste", total)
else:
    st.info("Votre liste est vide. Faites une recherche ci-dessus pour commencer.")
