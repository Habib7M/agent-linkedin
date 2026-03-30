"""Recherche automatique de prospects sur LinkedIn via recherche web.

Utilise Google Search (scraping) puis DuckDuckGo en fallback.
Fonctionne depuis les serveurs cloud (Streamlit Cloud).
"""

import re
import time
import httpx
import structlog
from typing import Optional
from urllib.parse import quote_plus, unquote

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

        prospects.append(_build_prospect(name, headline, about, linkedin_url))

    return prospects


# =============================================
# Méthode 1 : Google Search (scraping HTML)
# =============================================

def _search_google(search_query: str, max_results: int) -> list[dict]:
    """Recherche via Google Search scraping."""
    results = []
    num = min(max_results + 10, 40)
    url = f"https://www.google.com/search?q={quote_plus(search_query)}&num={num}&hl=fr"

    resp = httpx.get(url, headers=HEADERS, timeout=15.0, follow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    # Google met les résultats dans des <div class="g">
    # Chaque résultat a un <a href="..."> et un <h3>titre</h3>
    # On extrait avec regex

    # Pattern pour extraire URL + titre depuis les résultats Google
    # Les liens LinkedIn sont dans des <a href="/url?q=https://...linkedin.com/in/...">
    link_pattern = re.compile(
        r'<a\s+[^>]*href="/url\?q=(https?://[^"&]+linkedin\.com/in/[^"&]+)[^"]*"[^>]*>.*?<h3[^>]*>(.*?)</h3>',
        re.DOTALL
    )

    matches = link_pattern.findall(html)

    if not matches:
        # Fallback : pattern alternatif pour Google
        alt_pattern = re.compile(
            r'<a\s+[^>]*href="(https?://(?:www\.)?linkedin\.com/in/[^"]+)"[^>]*>.*?<h3[^>]*>(.*?)</h3>',
            re.DOTALL
        )
        matches = alt_pattern.findall(html)

    if not matches:
        # Pattern encore plus large : chercher tous les liens LinkedIn dans la page
        url_pattern = re.compile(r'(https?://(?:www\.)?linkedin\.com/in/[\w\-]+)')
        title_pattern = re.compile(r'<h3[^>]*>(.*?)</h3>', re.DOTALL)

        urls_found = url_pattern.findall(html)
        titles_found = title_pattern.findall(html)

        for i, u in enumerate(urls_found):
            title = titles_found[i] if i < len(titles_found) else ""
            title = re.sub(r'<[^>]+>', '', title).strip()
            matches.append((u, title))

    for href, title in matches:
        clean_url = unquote(href.split("&")[0])
        clean_title = re.sub(r'<[^>]+>', '', title).strip()

        results.append({
            "href": clean_url,
            "title": clean_title,
            "body": "",
        })

    log.info("google_search_results", count=len(results))
    return results


# =============================================
# Méthode 2 : Bing Search (fallback)
# =============================================

def _search_bing(search_query: str, max_results: int) -> list[dict]:
    """Recherche via Bing Search scraping."""
    results = []
    url = f"https://www.bing.com/search?q={quote_plus(search_query)}&count={min(max_results + 10, 50)}&setlang=fr"

    resp = httpx.get(url, headers=HEADERS, timeout=15.0, follow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    # Bing : <li class="b_algo"><h2><a href="URL">Titre</a></h2><p>snippet</p></li>
    pattern = re.compile(
        r'<li\s+class="b_algo"[^>]*>.*?<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?(?:<p[^>]*>(.*?)</p>)?',
        re.DOTALL
    )

    for href, title, snippet in pattern.findall(html):
        clean_title = re.sub(r'<[^>]+>', '', title).strip()
        clean_snippet = re.sub(r'<[^>]+>', '', snippet).strip() if snippet else ""

        results.append({
            "href": href,
            "title": clean_title,
            "body": clean_snippet,
        })

    log.info("bing_search_results", count=len(results))
    return results


# =============================================
# Méthode 3 : DuckDuckGo package (dernier recours)
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

    Essaie dans l'ordre : Google → Bing → DuckDuckGo package.
    """
    search_query = f"site:linkedin.com/in {query}"
    log.info("prospect_search_start", query=search_query, max_results=max_results)

    methods = [
        ("google", lambda: _search_google(search_query, max_results)),
        ("bing", lambda: _search_bing(search_query, max_results)),
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
                    log.warning("no_linkedin_profiles_in_results", method=method_name, raw_count=len(raw_results))
        except Exception as e:
            log.warning("search_method_failed", method=method_name, error=str(e))
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
