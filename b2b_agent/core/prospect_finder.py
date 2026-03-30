"""Recherche automatique de prospects sur LinkedIn via Brave Search.

Brave Search est le seul moteur qui accepte les requêtes depuis
les serveurs cloud (Streamlit Cloud). Parsing optimisé pour
extraire un maximum d'infos de chaque profil LinkedIn.
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


# =============================================
# Extraction d'infos depuis les résultats
# =============================================

def _extract_linkedin_url(url: str) -> Optional[str]:
    """Extrait et normalise l'URL LinkedIn d'un profil."""
    # Décoder les URL encodées (%C3%A8 → è, etc.)
    url = unquote(url)
    match = re.search(r"(https?://(?:www\.)?linkedin\.com/in/[\w\-]+)", url)
    if match:
        return match.group(1)
    return None


def _parse_title(title: str) -> dict:
    """Parse le titre Brave pour extraire nom + headline.

    Format typique : "Prénom Nom - Titre professionnel | LinkedIn"
    Le séparateur nom/headline a des ESPACES autour du tiret (pas les tirets dans les noms).
    """
    # Retirer " | LinkedIn" à la fin
    cleaned = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)

    # Séparer nom et headline — EXIGER des espaces autour du tiret
    # "Glaude-Brécy - Coach" → split sur " - " (avec espaces), pas sur "-" dans le nom
    parts = re.split(r"\s+[\-–—]\s+", cleaned, maxsplit=1)

    name = parts[0].strip()
    # Nettoyer le nom (garder lettres, accents, espaces, tirets, points)
    name = re.sub(r"[^\w\s\-éèêëàâäùûüôöîïçÉÈÊËÀÂÄÙÛÜÔÖÎÏÇ'.]", "", name).strip()

    headline = ""
    if len(parts) > 1:
        headline = parts[1].strip()
        headline = re.sub(r"<[^>]+>", "", headline).strip()

    return {"name": name, "headline": headline}


def _parse_description(desc: str) -> dict:
    """Parse la description Brave pour extraire des infos enrichies.

    Brave renvoie souvent : "Date - Experience: Titre · Location: Ville · X connections..."
    """
    info = {
        "experience": "",
        "education": "",
        "location": "",
        "connections": "",
        "about": "",
    }

    if not desc:
        return info

    # Nettoyer les balises HTML et entités
    desc = re.sub(r"<[^>]+>", "", desc)
    desc = desc.replace("&nbsp;", " ").replace("&amp;", "&").strip()

    # Extraire Experience
    exp_match = re.search(r"Experience:\s*(.+?)(?:\s*·|\s*$)", desc)
    if exp_match:
        info["experience"] = exp_match.group(1).strip()

    # Extraire Education
    edu_match = re.search(r"Education:\s*(.+?)(?:\s*·|\s*$)", desc)
    if edu_match:
        info["education"] = edu_match.group(1).strip()

    # Extraire Location
    loc_match = re.search(r"Location:\s*(.+?)(?:\s*·|\s*$)", desc)
    if loc_match:
        info["location"] = loc_match.group(1).strip()

    # Extraire Connections
    conn_match = re.search(r"(\d+\+?)\s*connect", desc, re.IGNORECASE)
    if conn_match:
        info["connections"] = conn_match.group(1)

    # Le reste comme "about" (texte libre au début, avant les champs structurés)
    about_text = desc
    # Retirer les dates au début
    about_text = re.sub(r"^\d{1,2}\s\w+\s\d{4}\s*[\-–—·]\s*", "", about_text)
    # Retirer les champs structurés
    about_text = re.sub(r"(?:Experience|Education|Location):\s*.+?(?:\s*·|\s*$)", "", about_text)
    about_text = re.sub(r"\d+\+?\s*connect.*$", "", about_text, flags=re.IGNORECASE)
    about_text = re.sub(r"View .+'s profile on LinkedIn.*$", "", about_text, flags=re.IGNORECASE)
    about_text = re.sub(r"Voir le profil de .+ sur LinkedIn.*$", "", about_text, flags=re.IGNORECASE)
    about_text = re.sub(r"Join now to see all activity", "", about_text)
    about_text = re.sub(r"·\s*·", "", about_text)
    about_text = re.sub(r"\s+", " ", about_text).strip(" ·-–—")

    if about_text and len(about_text) > 10:
        info["about"] = about_text

    return info


# =============================================
# Brave Search
# =============================================

def _brave_get(params: dict, max_retries: int = 3) -> str:
    """Fait une requête GET à Brave Search avec retries."""
    for attempt in range(max_retries):
        resp = httpx.get(
            "https://search.brave.com/search",
            params=params,
            headers=HEADERS,
            timeout=15.0,
            follow_redirects=True,
        )
        if resp.status_code == 429:
            wait = 2 ** attempt
            log.warning("brave_rate_limit", attempt=attempt + 1, wait=wait)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.text
    raise Exception("Brave Search temporairement indisponible. Réessayez dans 1 minute.")


def _search_brave(query: str, max_results: int) -> list[dict]:
    """Recherche via Brave Search avec parsing optimisé.

    Retourne une liste de dicts avec toutes les infos extraites.
    """
    search_query = f"site:linkedin.com/in {query}"
    html = _brave_get({"q": search_query, "source": "web"})

    # Parser avec le format Brave : data-pos, href, title, content
    result_pattern = re.compile(
        r'data-pos="(\d+)".*?'
        r'href="(https?://(?:www\.)?linkedin\.com/in/[^"]+)".*?'
        r'class="title search-snippet-title[^"]*"[^>]*>(.*?)</(?:span|div)>.*?'
        r'class="content desktop-default-regular[^"]*"[^>]*>(.*?)</(?:div|p)>',
        re.DOTALL
    )

    matches = result_pattern.findall(html)
    log.info("brave_raw_results", count=len(matches))

    prospects = []
    seen_urls = set()

    for pos, url, title_raw, desc_raw in matches:
        if len(prospects) >= max_results:
            break

        # Nettoyer le HTML
        title = re.sub(r"<[^>]+>", "", title_raw).strip()
        desc = re.sub(r"<[^>]+>", "", desc_raw).strip()

        # Extraire l'URL LinkedIn propre
        linkedin_url = _extract_linkedin_url(url)
        if not linkedin_url or linkedin_url in seen_urls:
            continue
        seen_urls.add(linkedin_url)

        # Parser le titre
        title_info = _parse_title(title)
        name = title_info["name"]
        headline = title_info["headline"]

        if not name or len(name) < 3:
            continue

        # Parser la description pour enrichir
        desc_info = _parse_description(desc)

        # L'experience LinkedIn = souvent le nom de l'entreprise/activité
        company = desc_info["experience"]
        # Si "experience" ressemble trop au headline, ne pas dupliquer
        if company and headline and company.lower() == headline.lower():
            company = ""

        # Construire le prospect enrichi
        prospect = {
            "name": name,
            "company": company,
            "email": "",
            "linkedin_url": linkedin_url,
            "role": headline,
            "industry": "",
            "custom_signal": "",
            "linkedin_headline": headline,
            "linkedin_about": desc_info["about"],
            "recent_activity": "",
            "skills": "",
            "experience_summary": desc_info["experience"],
            "pain_points": "",
            "mutual_context": "",
            "tone_preference": "",
            "location": desc_info["location"],
            "education": desc_info["education"],
            "connections": desc_info["connections"],
            "source": "recherche_auto",
        }
        prospects.append(prospect)

    return prospects


def _search_brave_page2(query: str, max_results: int) -> list[dict]:
    """Récupère la page 2 des résultats Brave pour avoir plus de prospects."""
    search_query = f"site:linkedin.com/in {query}"
    html = _brave_get({"q": search_query, "source": "web", "offset": 1})

    result_pattern = re.compile(
        r'data-pos="(\d+)".*?'
        r'href="(https?://(?:www\.)?linkedin\.com/in/[^"]+)".*?'
        r'class="title search-snippet-title[^"]*"[^>]*>(.*?)</(?:span|div)>.*?'
        r'class="content desktop-default-regular[^"]*"[^>]*>(.*?)</(?:div|p)>',
        re.DOTALL
    )

    matches = result_pattern.findall(html)
    prospects = []
    seen_urls = set()

    for pos, url, title_raw, desc_raw in matches:
        if len(prospects) >= max_results:
            break

        title = re.sub(r"<[^>]+>", "", title_raw).strip()
        desc = re.sub(r"<[^>]+>", "", desc_raw).strip()

        linkedin_url = _extract_linkedin_url(url)
        if not linkedin_url or linkedin_url in seen_urls:
            continue
        seen_urls.add(linkedin_url)

        title_info = _parse_title(title)
        name = title_info["name"]
        headline = title_info["headline"]

        if not name or len(name) < 3:
            continue

        desc_info = _parse_description(desc)
        company = desc_info["experience"]
        if company and headline and company.lower() == headline.lower():
            company = ""

        prospect = {
            "name": name,
            "company": company,
            "email": "",
            "linkedin_url": linkedin_url,
            "role": headline,
            "industry": "",
            "custom_signal": "",
            "linkedin_headline": headline,
            "linkedin_about": desc_info["about"],
            "recent_activity": "",
            "skills": "",
            "experience_summary": desc_info["experience"],
            "pain_points": "",
            "mutual_context": "",
            "tone_preference": "",
            "location": desc_info["location"],
            "education": desc_info["education"],
            "connections": desc_info["connections"],
            "source": "recherche_auto",
        }
        prospects.append(prospect)

    return prospects


# =============================================
# Fonctions publiques
# =============================================

def search_prospects(
    query: str,
    max_results: int = 20,
    region: str = "fr-fr",
) -> list[dict]:
    """Recherche des profils LinkedIn correspondant à la requête.

    Utilise Brave Search avec parsing enrichi.
    Si besoin de plus de résultats, récupère aussi la page 2.
    """
    log.info("prospect_search_start", query=query, max_results=max_results)

    try:
        # Page 1
        prospects = _search_brave(query, max_results)

        # Si on a besoin de plus, récupérer page 2
        if len(prospects) < max_results:
            time.sleep(0.5)
            try:
                page2 = _search_brave_page2(query, max_results - len(prospects))
                # Dédupliquer
                seen = {p["linkedin_url"] for p in prospects}
                for p in page2:
                    if p["linkedin_url"] not in seen:
                        prospects.append(p)
                        seen.add(p["linkedin_url"])
                        if len(prospects) >= max_results:
                            break
            except Exception as e:
                log.warning("page2_failed", error=str(e))

        log.info("prospect_search_done", found=len(prospects))
        return prospects

    except Exception as e:
        log.error("prospect_search_error", error=str(e))
        raise


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
