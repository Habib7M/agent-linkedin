"""Recherche automatique de prospects sur LinkedIn via recherche web.

Utilise des instances SearXNG (moteur de recherche libre) qui agrègent
Google, Bing, DuckDuckGo, etc. Fonctionne depuis les serveurs cloud.
"""

import re
import time
import random
import httpx
import structlog
from typing import Optional
from urllib.parse import quote_plus, unquote

log = structlog.get_logger()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}

# Instances SearXNG publiques avec API JSON activée
SEARXNG_INSTANCES = [
    "https://search.sapti.me",
    "https://searx.tiekoetter.com",
    "https://search.bus-hit.me",
    "https://searx.be",
    "https://search.neet.works",
    "https://searx.oxf.te.uk",
    "https://search.ononoki.org",
    "https://searx.namejeff.xyz",
    "https://priv.au",
]


def _extract_name_from_title(title: str) -> str:
    """Extrait le nom depuis le titre d'un profil LinkedIn."""
    cleaned = re.sub(r"\s*[\|\-–—]\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
    parts = re.split(r"\s*[\-–—]\s*", cleaned, maxsplit=1)
    name = parts[0].strip()
    name = re.sub(r"[^\w\s\-éèêëàâäùûüôöîïçÉÈÊËÀÂÄÙÛÜÔÖÎÏÇ']", "", name)
    return name.strip()


def _extract_headline_from_title(title: str) -> str:
    """Extrait le headline depuis le titre d'un résultat LinkedIn."""
    cleaned = re.sub(r"\s*[\|]\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
    parts = re.split(r"\s*[\-–—]\s*", cleaned, maxsplit=1)
    if len(parts) > 1:
        return parts[1].strip()
    return ""


def _extract_linkedin_url(url: str) -> Optional[str]:
    """Extrait et normalise l'URL LinkedIn d'un profil."""
    match = re.search(r"(https?://(?:www\.)?linkedin\.com/in/[\w\-]+)", url)
    if match:
        return match.group(1)
    return None


def _extract_about_from_snippet(snippet: str) -> str:
    """Extrait un résumé depuis le snippet de recherche."""
    cleaned = snippet.strip()
    cleaned = re.sub(r"^\d{1,2}\s\w+\s\d{4}\s*[\-–—·]\s*", "", cleaned)
    cleaned = re.sub(r"^Voir le profil de .+ sur LinkedIn.*?\.", "", cleaned)
    cleaned = re.sub(r"^View .+'s profile on LinkedIn.*?\.", "", cleaned)
    # Nettoyer les tags HTML restants
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    return cleaned.strip()


def _build_prospect(name: str, headline: str, about: str, linkedin_url: str) -> dict:
    """Construit un dict prospect standard."""
    return {
        "name": name,
        "company": "",
        "email": "",
        "linkedin_url": linkedin_url,
        "role": headline,
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


def _parse_results(results: list[dict], max_results: int) -> list[dict]:
    """Parse les résultats bruts en prospects structurés."""
    prospects = []
    seen_urls = set()

    for result in results:
        if len(prospects) >= max_results:
            break

        url = result.get("href", result.get("url", ""))
        title = result.get("title", "")
        snippet = result.get("body", result.get("snippet", result.get("content", "")))

        linkedin_url = _extract_linkedin_url(url)
        if not linkedin_url:
            continue

        if linkedin_url in seen_urls:
            continue
        seen_urls.add(linkedin_url)

        name = _extract_name_from_title(title)
        headline = _extract_headline_from_title(title)
        about = _extract_about_from_snippet(snippet)

        if not name or len(name) < 3:
            continue

        prospects.append(_build_prospect(name, headline, about, linkedin_url))

    return prospects


# =============================================
# Méthode principale : SearXNG (instances publiques)
# =============================================

def _search_searxng(search_query: str, max_results: int) -> list[dict]:
    """Recherche via une instance SearXNG publique (API JSON)."""
    # Mélanger les instances pour répartir la charge
    instances = SEARXNG_INSTANCES.copy()
    random.shuffle(instances)

    for instance in instances:
        try:
            url = f"{instance}/search"
            params = {
                "q": search_query,
                "format": "json",
                "language": "fr",
                "categories": "general",
                "pageno": 1,
            }

            resp = httpx.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=10.0,
                follow_redirects=True,
            )

            if resp.status_code != 200:
                log.warning("searxng_bad_status", instance=instance, status=resp.status_code)
                continue

            data = resp.json()
            results = data.get("results", [])

            if results:
                # Convertir au format standard
                formatted = []
                for r in results:
                    formatted.append({
                        "href": r.get("url", ""),
                        "title": r.get("title", ""),
                        "body": r.get("content", ""),
                    })
                log.info("searxng_success", instance=instance, count=len(formatted))
                return formatted

        except Exception as e:
            log.warning("searxng_instance_failed", instance=instance, error=str(e))
            continue

    return []


# =============================================
# Fallback : DuckDuckGo package
# =============================================

def _search_ddg_package(search_query: str, max_results: int, region: str) -> list[dict]:
    """Recherche via le package duckduckgo-search."""
    try:
        from duckduckgo_search import DDGS
        ddgs = DDGS()
        results = list(ddgs.text(
            search_query,
            region=region,
            max_results=max_results + 10,
        ))
        return results
    except ImportError:
        log.warning("duckduckgo_search_not_installed")
        return []


# =============================================
# Fonction principale
# =============================================

def search_prospects(
    query: str,
    max_results: int = 20,
    region: str = "fr-fr",
) -> list[dict]:
    """Recherche des profils LinkedIn correspondant à la requête.

    Essaie dans l'ordre : SearXNG → DuckDuckGo package.
    """
    search_query = f"site:linkedin.com/in {query}"
    log.info("prospect_search_start", query=search_query, max_results=max_results)

    methods = [
        ("searxng", lambda: _search_searxng(search_query, max_results)),
        ("ddg_package", lambda: _search_ddg_package(search_query, max_results, region)),
    ]

    for method_name, search_fn in methods:
        try:
            raw_results = search_fn()
            if raw_results:
                prospects = _parse_results(raw_results, max_results)
                if prospects:
                    log.info("prospect_search_done", method=method_name, found=len(prospects))
                    return prospects
                else:
                    log.warning("no_linkedin_in_results", method=method_name, raw_count=len(raw_results))
        except Exception as e:
            log.warning("search_failed", method=method_name, error=str(e))
        time.sleep(0.5)

    log.warning("prospect_search_empty", query=search_query)
    return []


def search_multiple_queries(
    queries: list[str],
    max_per_query: int = 10,
    region: str = "fr-fr",
) -> list[dict]:
    """Lance plusieurs recherches et combine les résultats sans doublons."""
    all_prospects = []
    seen_urls = set()

    for query in queries:
        results = search_prospects(query, max_results=max_per_query, region=region)
        for prospect in results:
            if prospect["linkedin_url"] not in seen_urls:
                seen_urls.add(prospect["linkedin_url"])
                all_prospects.append(prospect)
        time.sleep(1)

    return all_prospects
