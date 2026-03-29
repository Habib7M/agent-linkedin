"""Agent IA de Prospection LinkedIn — Accueil + Connexion."""

import streamlit as st
from core.auth import (
    authenticate, create_client, is_admin, list_clients,
    delete_client, get_client_display_name, ensure_admin_exists,
    change_password, update_quota, get_usage,
)
from core.db import init_db, get_total_prospects, count_prospects_by_status

# Créer le compte admin au premier lancement
ensure_admin_exists()

st.set_page_config(
    page_title="Agent Prospection LinkedIn",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --- Système de connexion ---

def show_login():
    """Affiche la page de connexion."""
    st.title("🔐 Connexion")
    st.markdown("Entrez vos identifiants pour accéder à votre espace.")
    st.markdown("")

    with st.form("login_form"):
        username = st.text_input("Identifiant")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter", type="primary")

    if submitted:
        if not username or not password:
            st.error("Remplissez les deux champs.")
        elif authenticate(username, password):
            st.session_state["client_id"] = username
            st.session_state["logged_in"] = True
            st.session_state["display_name"] = get_client_display_name(username)
            st.rerun()
        else:
            st.error("Identifiant ou mot de passe incorrect.")


def show_admin_panel():
    """Section admin pour gérer les clients."""
    st.markdown("---")
    st.markdown("### 👑 Espace Admin")

    tab1, tab2, tab3 = st.tabs(["Créer un client", "Clients & Quotas", "Mot de passe"])

    with tab1:
        with st.form("create_client_form"):
            new_user = st.text_input("Identifiant du client (sans espaces)")
            new_name = st.text_input("Nom affiché (ex: Marie Dupont)")
            new_pass = st.text_input("Mot de passe", type="password")
            new_pass2 = st.text_input("Confirmer le mot de passe", type="password")
            create_btn = st.form_submit_button("Créer le compte", type="primary")

        if create_btn:
            if not new_user or not new_pass:
                st.error("Remplissez tous les champs.")
            elif " " in new_user:
                st.error("L'identifiant ne doit pas contenir d'espaces.")
            elif new_pass != new_pass2:
                st.error("Les mots de passe ne correspondent pas.")
            elif len(new_pass) < 6:
                st.error("Le mot de passe doit faire au moins 6 caractères.")
            else:
                if create_client(new_user, new_pass, new_name):
                    st.success(f"Compte créé pour **{new_name or new_user}** !")
                    old_client = st.session_state.get("client_id", "")
                    st.session_state["client_id"] = new_user
                    init_db()
                    st.session_state["client_id"] = old_client
                else:
                    st.error("Ce nom d'utilisateur existe déjà.")

    with tab2:
        clients = list_clients()
        if not clients:
            st.info("Aucun client pour le moment.")
        else:
            st.markdown(f"**{len(clients)} compte(s)**")
            st.markdown("")

            for c in clients:
                if c["username"] == "admin":
                    continue

                with st.expander(f"**{c['display_name']}** (`{c['username']}`)"):
                    # Utilisation du mois
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Prospects** : {c['used_prospects']} / {c['quota_prospects']}")
                    with col2:
                        st.markdown(f"**Messages IA** : {c['used_messages']} / {c['quota_messages']}")

                    # Modifier les quotas
                    with st.form(f"quota_{c['username']}"):
                        qcol1, qcol2 = st.columns(2)
                        with qcol1:
                            new_qp = st.number_input(
                                "Quota prospects/mois",
                                value=c["quota_prospects"],
                                min_value=0, max_value=10000, step=50,
                                key=f"qp_{c['username']}",
                            )
                        with qcol2:
                            new_qm = st.number_input(
                                "Quota messages/mois",
                                value=c["quota_messages"],
                                min_value=0, max_value=10000, step=50,
                                key=f"qm_{c['username']}",
                            )

                        bcol1, bcol2 = st.columns(2)
                        with bcol1:
                            if st.form_submit_button("💾 Modifier le quota"):
                                update_quota(c["username"], new_qp, new_qm)
                                st.success("Quota mis à jour !")
                                st.rerun()
                        with bcol2:
                            if st.form_submit_button("🗑 Supprimer le client"):
                                delete_client(c["username"])
                                st.rerun()

    with tab3:
        with st.form("change_pwd_form"):
            old_pwd = st.text_input("Mot de passe actuel", type="password")
            new_pwd = st.text_input("Nouveau mot de passe", type="password")
            new_pwd2 = st.text_input("Confirmer le nouveau mot de passe", type="password")
            change_btn = st.form_submit_button("Changer le mot de passe", type="primary")

        if change_btn:
            client_id = st.session_state.get("client_id", "")
            if not old_pwd or not new_pwd:
                st.error("Remplissez tous les champs.")
            elif not authenticate(client_id, old_pwd):
                st.error("Mot de passe actuel incorrect.")
            elif new_pwd != new_pwd2:
                st.error("Les nouveaux mots de passe ne correspondent pas.")
            elif len(new_pwd) < 6:
                st.error("Le mot de passe doit faire au moins 6 caractères.")
            else:
                change_password(client_id, new_pwd)
                st.success("Mot de passe changé ! ✅")


def show_home():
    """Page d'accueil après connexion."""
    display = st.session_state.get("display_name", "")
    client_id = st.session_state.get("client_id", "")

    st.title("🚀 Agent de Prospection LinkedIn")
    st.markdown(f"Bienvenue **{display}** !")
    st.markdown("---")

    init_db()

    total = get_total_prospects()

    if total == 0:
        st.markdown("### Comment ça marche ?")
        st.markdown("")
        st.markdown("**Étape 1** — Allez dans **⚙️ Réglages** pour configurer votre offre")
        st.markdown("**Étape 2** — Allez dans **🔍 Prospects** et trouvez vos futurs clients")
        st.markdown("**Étape 3** — Allez dans **🚀 Campagne** et l'IA écrit les messages pour vous")
        st.markdown("**Étape 4** — Suivez les résultats dans **📊 Suivi**")
    else:
        status_counts = count_prospects_by_status()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Prospects", total)
        col2.metric("Contactés", status_counts.get("contacted", 0))
        col3.metric("Réponses", status_counts.get("replied", 0))
        col4.metric("RDV décrochés", status_counts.get("meeting_booked", 0))

    # Panneau admin si connecté en admin
    if is_admin(client_id):
        show_admin_panel()


# --- Barre latérale ---

def show_sidebar():
    """Affiche le bouton déconnexion dans la barre latérale."""
    with st.sidebar:
        st.markdown("---")
        display = st.session_state.get("display_name", "")
        st.markdown(f"Connecté : **{display}**")
        if st.button("🚪 Se déconnecter"):
            for key in ["client_id", "logged_in", "display_name"]:
                st.session_state.pop(key, None)
            st.rerun()


# --- Point d'entrée ---

if st.session_state.get("logged_in"):
    show_sidebar()
    show_home()
else:
    show_login()
