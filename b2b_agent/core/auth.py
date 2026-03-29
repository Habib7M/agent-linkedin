"""Authentification et gestion des clients.

Chaque client a :
- Un identifiant unique (username)
- Un mot de passe
- Sa propre base de données SQLite (isolation complète)

Les clients sont stockés dans data/clients.json.
"""

import json
import hashlib
import secrets
from pathlib import Path

CLIENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "clients.json"


def _hash_password(password: str, salt: str = "") -> str:
    """Hash un mot de passe avec un sel."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def _verify_password(password: str, stored: str) -> bool:
    """Vérifie un mot de passe contre le hash stocké."""
    salt = stored.split(":")[0]
    return _hash_password(password, salt) == stored


def _load_clients() -> dict:
    """Charge la liste des clients."""
    CLIENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CLIENTS_FILE.exists():
        return json.loads(CLIENTS_FILE.read_text(encoding="utf-8"))
    return {}


def _save_clients(clients: dict):
    """Sauvegarde la liste des clients."""
    CLIENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CLIENTS_FILE.write_text(json.dumps(clients, indent=2, ensure_ascii=False), encoding="utf-8")


def create_client(username: str, password: str, display_name: str = "") -> bool:
    """Crée un nouveau client. Retourne True si créé, False si existe déjà."""
    clients = _load_clients()
    if username in clients:
        return False

    clients[username] = {
        "password": _hash_password(password),
        "display_name": display_name or username,
    }
    _save_clients(clients)
    return True


def authenticate(username: str, password: str) -> bool:
    """Vérifie les identifiants d'un client."""
    clients = _load_clients()
    if username not in clients:
        return False
    return _verify_password(password, clients[username]["password"])


def get_client_display_name(username: str) -> str:
    """Retourne le nom d'affichage d'un client."""
    clients = _load_clients()
    if username in clients:
        return clients[username].get("display_name", username)
    return username


def list_clients() -> list:
    """Liste tous les clients (sans mots de passe)."""
    clients = _load_clients()
    return [{"username": k, "display_name": v.get("display_name", k)} for k, v in clients.items()]


def delete_client(username: str) -> bool:
    """Supprime un client."""
    clients = _load_clients()
    if username in clients:
        del clients[username]
        _save_clients(clients)
        return True
    return False


def get_client_db_path(username: str) -> Path:
    """Retourne le chemin de la base de données d'un client."""
    return Path(__file__).resolve().parent.parent / "data" / f"client_{username}.db"


def is_admin(username: str) -> bool:
    """Vérifie si un utilisateur est l'admin."""
    return username == "admin"
