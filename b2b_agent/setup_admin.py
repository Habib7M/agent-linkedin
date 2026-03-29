"""Script pour créer le compte admin initial."""

from core.auth import create_client

# Crée le compte admin avec le mot de passe par défaut
# IMPORTANT : changez ce mot de passe après la première connexion !
if create_client("admin", "admin123", "Administrateur"):
    print("✅ Compte admin créé !")
    print("   Identifiant : admin")
    print("   Mot de passe : admin123")
    print("   ⚠️  Pensez à changer ce mot de passe !")
else:
    print("Le compte admin existe déjà.")
