"""Recherche automatique de prospects sur LinkedIn via recherche web.

Utilise DuckDuckGo pour trouver des profils LinkedIn correspondant
aux critères de recherche (ex: "coach de vie Paris").

Fallback sur recherche HTTP directe si le package DDG ne fonctionne pas.
"""

import re
import time
import httpx
import structlog
from typing import Optional
from urllib.parse import quote_plus

log = structlog.get_logger()


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
    return cleaned.strip()


def _parse_results(results: list[dict], max_results: int) -> list[dict]:
    """Parse les résultats bruts en prospects structurés."""
    prospects = []
    seen_urls = set()

    for result in results:
        if len(prospects) >= max_results:
            break

        url = result.get("href", result.get("url", ""))
        title = result.get("title", "")
        snippet = result.get("body", result.get("snippet", ""))

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

        prospect = {
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
        prospects.append(prospect)

    return prospects


def _search_ddg_package(search_query: str, max_results: int, region: str) -> list[dict]:
    """Recherche via le package duckduckgo-search."""
    from duckduckgo_search import DDGS

    ddgs = DDGS()
    results = list(ddgs.text(
        search_query,
        region=region,
        max_results=max_results + 10,
    ))
    return results


def _search_ddg_http(search_query: str, max_results: int) -> list[dict]:
    """Recherche via l'API DuckDuckGo HTML directement (fallback)."""
    results = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    # Utiliser DuckDuckGo HTML
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(search_query)}"

    try:
        resp = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text

        # Parser les résultats avec regex
        # Format DDG HTML: <a class="result__a" href="...">titre</a>
        # et <a class="result__snippet">snippet</a>

        # Extraire les liens et titres
        link_pattern = re.compile(
            r'<a\s+[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL
        )
        snippet_pattern = re.compile(
            r'<a\s+[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (href, title) in enumerate(links):
            # Nettoyer le HTML des titres
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            clean_snippet = ""
            if i < len(snippets):
                clean_snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()

            # DDG encode les URLs, extraire le vrai lien
            real_url = href
            uddg_match = re.search(r'uddg=([^&]+)', href)
            if uddg_match:
                from urllib.parse import unquote
                real_url = unquote(uddg_match.group(1))

            results.append({
                "href": real_url,
                "title": clean_title,
                "body": clean_snippet,
            })

    except Exception as e:
        log.error("ddg_http_error", error=str(e))

    return results


def search_prospects(
    query: str,
    max_results: int = 20,
    region: str = "fr-fr",
) -> list[dict]:
    """Recherche des profils LinkedIn correspondant à la requête.

    Essaie d'abord le package duckduckgo-search, puis fallback sur HTTP direct.
    """
    search_query = f"site:linkedin.com/in {query}"
    log.info("prospect_search_start", query=search_query, max_results=max_results)

    # Méthode 1 : package duckduckgo-search
    try:
        raw_results = _search_ddg_package(search_query, max_results, region)
        if raw_results:
            prospects = _parse_results(raw_results, max_results)
            if prospects:
                log.info("prospect_search_done", method="ddg_package", found=len(prospects))
                return prospects
    except Exception as e:
        log.warning("ddg_package_failed", error=str(e))

    # Méthode 2 : HTTP direct (fallback)
    try:
        raw_results = _search_ddg_http(search_query, max_results)
        if raw_results:
            prospects = _parse_results(raw_results, max_results)
            if prospects:
                log.info("prospect_search_done", method="ddg_http", found=len(prospects))
                return prospects
    except Exception as e:
        log.warning("ddg_http_failed", error=str(e))

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
