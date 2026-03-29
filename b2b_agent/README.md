# Agent IA de Prospection B2B

Assistant de prospection LinkedIn & Email pour coachs en développement personnel.
Messages personnalisés par IA, zéro compétence technique requise.

## Installation locale

```bash
pip install -r requirements.txt
cp .env.example .env  # puis éditez avec vos clés
streamlit run app.py
```

L'app s'ouvre sur `http://localhost:8501`.

## Pages de l'interface

### 1. Upload Prospects
- Importez votre liste CSV (colonnes : name, company + optionnelles)
- Validation automatique, détection doublons, scoring

### 2. Templates
- Éditez vos messages par canal (email/LinkedIn), étape (cold, follow-up, breakup), variante (A/B)
- Prévisualisez avec un prospect réel via l'IA

### 3. Lancer Campagne
- Choisissez vos paramètres (rate limit, score min, dry-run)
- Lancez la séquence : LinkedIn J+0 > Email J+3 > LinkedIn J+7 > Email J+14

### 4. Tableau de Bord
- KPIs en temps réel : envoyés, réponses, bounces, meetings
- Résultats A/B testing, export CSV

### 5. Configuration
- Clés API (OpenAI), SMTP, IMAP, webhook
- Contexte coach (produit, ICP, value prop) utilisé pour personnaliser les messages

## Déploiement Streamlit Cloud

1. Poussez le repo sur GitHub
2. Allez sur [share.streamlit.io](https://share.streamlit.io)
3. Cliquez **New app** > sélectionnez votre repo > branche `main` > fichier `app.py`
4. Dans **Advanced settings > Secrets**, collez le contenu de votre `.env` au format TOML :
   ```toml
   OPENAI_API_KEY = "sk-..."
   SMTP_HOST = "smtp.gmail.com"
   SMTP_PORT = "587"
   SMTP_USER = "vous@gmail.com"
   SMTP_PASSWORD = "votre-mdp"
   SMTP_SENDER_NAME = "Marie Dupont"
   APP_PASSWORD = "mon-mot-de-passe"
   COACH_PRODUCT = "Mon programme..."
   COACH_ICP = "Mes clients..."
   COACH_VALUE_PROP = "Ma méthode..."
   ```
5. Cliquez **Deploy** — votre app est en ligne.

## Déploiement Railway (alternatif)

1. Poussez le repo sur GitHub
2. Sur [railway.app](https://railway.app), créez un nouveau projet depuis GitHub
3. Ajoutez les variables d'environnement dans le dashboard
4. Railway détecte automatiquement le `Procfile`
5. Votre app est déployée avec un domaine custom possible

## Configuration Gmail

Pour utiliser Gmail comme SMTP/IMAP :
1. Activez la vérification en 2 étapes sur votre compte Google
2. Créez un **mot de passe d'application** : Google Account > Sécurité > Mots de passe des applications
3. Utilisez ce mot de passe dans `SMTP_PASSWORD` et `IMAP_PASSWORD`

## Structure

```
b2b_agent/
├── app.py              # Point d'entrée Streamlit
├── pages/              # 5 pages Streamlit
├── core/               # Logique métier
├── templates/          # Templates de messages (modifiables via UI)
├── data/               # SQLite + exemple CSV
└── .streamlit/         # Config thème
```
