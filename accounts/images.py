import requests
from django.conf import settings

# Unified result shape:
# { "thumb": str, "url": str, "page": str, "title": str, "source": str, "credit_html": str }

def _unsplash_search(query: str, count: int):
    key = settings.UNSPLASH_ACCESS_KEY
    if not key:
        return []
    try:
        r = requests.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query": query,
                "per_page": min(count, 10),
                "orientation": "landscape",
                "content_filter": "high",
            },
            headers={"Authorization": f"Client-ID {key}"},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for p in (data.get("results") or []):
            user = p.get("user") or {}
            name = user.get("name") or "Photographer"
            username = user.get("username") or ""
            page = p.get("links", {}).get("html") or p.get("links", {}).get("download_location") or ""
            credit = f'Photo by <a href="https://unsplash.com/@{username}" target="_blank" rel="noopener">{name}</a> on <a href="https://unsplash.com" target="_blank" rel="noopener">Unsplash</a>'
            out.append({
                "thumb": (p.get("urls") or {}).get("small") or (p.get("urls") or {}).get("thumb"),
                "url": (p.get("urls") or {}).get("full") or (p.get("urls") or {}).get("regular"),
                "page": page,
                "title": p.get("alt_description") or "",
                "source": "Unsplash",
                "credit_html": credit,
            })
        return out
    except Exception:
        return []

def _pexels_search(query: str, count: int):
    key = settings.PEXELS_API_KEY
    if not key:
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": min(count, 10), "orientation": "landscape"},
            headers={"Authorization": key},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for p in (data.get("photos") or []):
            user = p.get("photographer") or "Photographer"
            user_url = p.get("photographer_url") or "https://www.pexels.com"
            page = p.get("url") or user_url
            credit = f'Photo by <a href="{user_url}" target="_blank" rel="noopener">{user}</a> on <a href="https://www.pexels.com" target="_blank" rel="noopener">Pexels</a>'
            src = p.get("src") or {}
            out.append({
                "thumb": src.get("medium") or src.get("small"),
                "url": src.get("large2x") or src.get("large") or src.get("original"),
                "page": page,
                "title": p.get("alt") or "",
                "source": "Pexels",
                "credit_html": credit,
            })
        return out
    except Exception:
        return []

def search_images(query: str, count: int = 10):
    return _pexels_search(query, count)
    