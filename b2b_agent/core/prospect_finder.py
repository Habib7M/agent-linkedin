"""Recherche automatique de prospects sur LinkedIn via Brave Search.

Brave Search fonctionne depuis les serveurs cloud (contrairement à
Google, Bing et DuckDuckGo qui bloquent les requêtes automatisées).
"""

import re
import time
import httpx
import structlog
from typing import Optional
from urllib.parse import quote_plus

log = structlog.get_logger()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}


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
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"^\d{1,2}\s\w+\s\d{4}\s*[\-–—·]\s*", "", cleaned)
    cleaned = re.sub(r"^Voir le profil de .+ sur LinkedIn.*?\.", "", cleaned)
    cleaned = re.sub(r"^View .+'s profile on LinkedIn.*?\.", "", cleaned)
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


def _search_brave(search_query: str, max_results: int) -> list[dict]:
    """Recherche via Brave Search (scraping HTML).

    Brave ne bloque pas les requêtes depuis les serveurs cloud.
    """
    results = []

    resp = httpx.get(
        "https://search.brave.com/search",
        params={"q": search_query, "source": "web"},
        headers=HEADERS,
        timeout=15.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    html = resp.text

    # Extraire les résultats Brave Search
    # Format: <a href="https://linkedin.com/in/...">
    # avec <span class="snippet-title">Titre</span>
    # et <p class="snippet-description">Description</p>

    # Pattern 1 : extraire blocs de résultats
    result_pattern = re.compile(
        r'<a[^>]*href="(https?://(?:www\.)?linkedin\.com/in/[^"]+)"[^>]*>.*?'
        r'(?:<span[^>]*>|<div[^>]*>)(.*?)(?:</span>|</div>)',
        re.DOTALL
    )

    for url, title_html in result_pattern.findall(html):
        clean_title = re.sub(r"<[^>]+>", "", title_html).strip()
        if clean_title and len(clean_title) > 3:
            results.append({
                "href": url,
                "title": clean_title,
                "body": "",
            })

    # Si pattern 1 ne marche pas, pattern plus large
    if not results:
        url_pattern = re.compile(r'href="(https?://(?:www\.)?linkedin\.com/in/[\w\-]+)"')
        urls_found = list(set(url_pattern.findall(html)))

        # Chercher les titres associés (balises <a> contenant ces URLs)
        for url in urls_found:
            # Chercher le titre dans le contexte autour du lien
            escaped_url = re.escape(url)
            title_match = re.search(
                rf'<a[^>]*href="{escaped_url}"[^>]*>(.*?)</a>',
                html,
                re.DOTALL,
            )
            title = ""
            if title_match:
                title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

            # Si pas de titre dans le <a>, chercher un <h3> ou <span> proche
            if not title or len(title) < 3:
                context_match = re.search(
                    rf'.{{0,500}}{escaped_url}.{{0,500}}',
                    html,
                    re.DOTALL,
                )
                if context_match:
                    ctx = context_match.group(0)
                    h_match = re.search(r'<(?:h[23]|span)[^>]*>(.*?)</(?:h[23]|span)>', ctx, re.DOTALL)
                    if h_match:
                        title = re.sub(r"<[^>]+>", "", h_match.group(1)).strip()

            results.append({
                "href": url,
                "title": title or url.split("/in/")[-1].replace("-", " ").title(),
                "body": "",
            })

    # Chercher aussi les snippets/descriptions pour enrichir
    for i, result in enumerate(results):
        url_escaped = re.escape(result["href"])
        snippet_match = re.search(
            rf'{url_escaped}.*?<p[^>]*>(.*?)</p>',
            html,
            re.DOTALL,
        )
        if snippet_match:
            results[i]["body"] = re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip()

    log.info("brave_search_results", count=len(results))
    return results


def _parse_to_prospects(results: list[dict], max_results: int) -> list[dict]:
    """Convertit les résultats bruts en prospects structurés."""
    prospects = []
    seen_urls = set()

    for result in results:
        if len(prospects) >= max_results:
            break

        url = result.get("href", "")
        title = result.get("title", "")
        snippet = result.get("body", "")

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


def search_prospects(
    query: str,
    max_results: int = 20,
    region: str = "fr-fr",
) -> list[dict]:
    """Recherche des profils LinkedIn correspondant à la requête."""
    search_query = f"site:linkedin.com/in {query}"
    log.info("prospect_search_start", query=search_query, max_results=max_results)

    # Méthode 1 : Brave Search
    try:
        raw_results = _search_brave(search_query, max_results)
        if raw_results:
            prospects = _parse_to_prospects(raw_results, max_results)
            if prospects:
                log.info("prospect_search_done", method="brave", found=len(prospects))
                return prospects
            else:
                log.warning("brave_no_linkedin", raw_count=len(raw_results))
    except Exception as e:
        log.warning("brave_failed", error=str(e))

    # Méthode 2 : DuckDuckGo package (fallback)
    try:
        from duckduckgo_search import DDGS
        ddgs = DDGS()
        raw = list(ddgs.text(search_query, region=region, max_results=max_results + 10))
        if raw:
            prospects = _parse_to_prospects(raw, max_results)
            if prospects:
                log.info("prospect_search_done", method="ddg", found=len(prospects))
                return prospects
    except Exception as e:
        log.warning("ddg_failed", error=str(e))

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
