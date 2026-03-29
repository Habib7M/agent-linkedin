"""Recherche automatique de prospects sur LinkedIn via recherche web.

Utilise DuckDuckGo pour trouver des profils LinkedIn correspondant
aux critères de recherche (ex: "coach de vie Paris").

Aucune clé API nécessaire — fonctionne immédiatement.
"""

import re
import time
import structlog
from typing import Optional
from duckduckgo_search import DDGS

log = structlog.get_logger()


def _extract_name_from_title(title: str) -> str:
    """Extrait le nom depuis le titre Google/DDG d'un profil LinkedIn.

    Format typique : "Prénom Nom - Titre | LinkedIn"
    """
    # Retirer " | LinkedIn", " - LinkedIn", etc.
    cleaned = re.sub(r"\s*[\|\-–—]\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
    # Retirer le titre après le tiret : "Prénom Nom - Coach de vie" → "Prénom Nom"
    parts = re.split(r"\s*[\-–—]\s*", cleaned, maxsplit=1)
    name = parts[0].strip()
    # Nettoyer les caractères spéciaux
    name = re.sub(r"[^\w\s\-éèêëàâäùûüôöîïçÉÈÊËÀÂÄÙÛÜÔÖÎÏÇ']", "", name)
    return name.strip()


def _extract_headline_from_title(title: str) -> str:
    """Extrait le headline depuis le titre d'un résultat LinkedIn.

    Format typique : "Prénom Nom - Coach de vie certifiée | LinkedIn"
    """
    # Retirer " | LinkedIn" à la fin
    cleaned = re.sub(r"\s*[\|]\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
    # Prendre après le premier tiret
    parts = re.split(r"\s*[\-–—]\s*", cleaned, maxsplit=1)
    if len(parts) > 1:
        return parts[1].strip()
    return ""


def _extract_linkedin_url(url: str) -> Optional[str]:
    """Extrait et normalise l'URL LinkedIn d'un profil."""
    # Chercher le pattern linkedin.com/in/...
    match = re.search(r"(https?://(?:www\.)?linkedin\.com/in/[\w\-]+)", url)
    if match:
        return match.group(1)
    return None


def _extract_about_from_snippet(snippet: str) -> str:
    """Extrait un résumé du 'about' depuis le snippet de recherche."""
    # Nettoyer les formats courants
    cleaned = snippet.strip()
    # Retirer les dates et préfixes inutiles
    cleaned = re.sub(r"^\d{1,2}\s\w+\s\d{4}\s*[\-–—·]\s*", "", cleaned)
    # Retirer "Voir le profil de..." patterns
    cleaned = re.sub(r"^Voir le profil de .+ sur LinkedIn.*?\.", "", cleaned)
    cleaned = re.sub(r"^View .+'s profile on LinkedIn.*?\.", "", cleaned)
    return cleaned.strip()


def search_prospects(
    query: str,
    max_results: int = 20,
    region: str = "fr-fr",
) -> list[dict]:
    """Recherche des profils LinkedIn correspondant à la requête.

    Args:
        query: recherche libre (ex: "coach de vie Paris", "coach parental Lyon")
        max_results: nombre max de résultats (défaut 20)
        region: région de recherche (défaut: France)

    Returns:
        Liste de dicts avec: name, linkedin_url, linkedin_headline, linkedin_about, source
    """
    # Construire la requête LinkedIn
    search_query = f"site:linkedin.com/in {query}"

    log.info("prospect_search_start", query=search_query, max_results=max_results)

    prospects = []
    seen_urls = set()

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                search_query,
                region=region,
                max_results=max_results + 10,  # marge pour les doublons/non-pertinents
            ))

        for result in results:
            if len(prospects) >= max_results:
                break

            url = result.get("href", "")
            title = result.get("title", "")
            snippet = result.get("body", "")

            # Filtrer : garder uniquement les profils LinkedIn /in/
            linkedin_url = _extract_linkedin_url(url)
            if not linkedin_url:
                continue

            # Éviter les doublons
            if linkedin_url in seen_urls:
                continue
            seen_urls.add(linkedin_url)

            # Extraire les infos
            name = _extract_name_from_title(title)
            headline = _extract_headline_from_title(title)
            about = _extract_about_from_snippet(snippet)

            # Ignorer les résultats sans nom exploitable
            if not name or len(name) < 3:
                continue

            prospect = {
                "name": name,
                "company": "",  # Non disponible dans les résultats de recherche
                "email": "",
                "linkedin_url": linkedin_url,
                "role": headline,  # Le headline sert de rôle
                "industry": "",
                "custom_signal": "",
                "linkedin_headline": headline,
                "linkedin_about": about,
                "recent_activity": "",
                "skills": "",
                "experience_summary": "",
                "pain_points": "",
                "mutual_context": "",
                "tone_preference": "",
                "source": "recherche_auto",
            }
            prospects.append(prospect)

        log.info("prospect_search_done", found=len(prospects))

    except Exception as e:
        log.error("prospect_search_error", error=str(e))
        raise

    return prospects


def search_multiple_queries(
    queries: list[str],
    max_per_query: int = 10,
    region: str = "fr-fr",
) -> list[dict]:
    """Lance plusieurs recherches et combine les résultats sans doublons.

    Args:
        queries: liste de requêtes (ex: ["coach de vie Paris", "coach de vie Lyon"])
        max_per_query: nombre max par requête
        region: région de recherche

    Returns:
        Liste combinée et dédupliquée de prospects
    """
    all_prospects = []
    seen_urls = set()

    for query in queries:
        results = search_prospects(query, max_results=max_per_query, region=region)
        for prospect in results:
            if prospect["linkedin_url"] not in seen_urls:
                seen_urls.add(prospect["linkedin_url"])
                all_prospects.append(prospect)
        # Petite pause entre les recherches pour ne pas être bloqué
        time.sleep(1)

    return all_prospects
