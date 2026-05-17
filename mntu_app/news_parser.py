import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from mntu_app.config import NEWS_URL, REQUEST_TIMEOUT, USER_AGENT

_READMORE_LABEL = re.compile(r"^(read more|читати(\s+далі)?|далі\s*→?)\s*$", re.I)

def _parse_istu_news_readmore_fallback(soup: BeautifulSoup, page_url: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    skip_title = re.compile(
        r"^(новини|зв'яжіться|освітні програми|міжнародний науково|мнту\s*[-—])",
        re.I,
    )
    for a in soup.find_all("a", href=True):
        label = (a.get_text(strip=True) or "").strip()
        if len(label) > 80:
            continue
        if not _READMORE_LABEL.match(label) and "read more" not in label.lower() and "читати" not in label.lower():
            continue
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if not href.startswith("http"):
            href = urljoin(page_url, href)
        if "istu.edu.ua" not in href:
            continue
        if "/category/" in href or "/author/" in href or "/tag/" in href:
            continue
        if href.rstrip("/") == NEWS_URL.rstrip("/"):
            continue
        if href in seen:
            continue
        seen.add(href)
        title = ""
        excerpt = ""
        date_str = ""
        prev = a
        for _ in range(50):
            prev = prev.find_previous(["h1", "h2", "h3", "h4"])
            if prev is None:
                break
            cand = prev.get_text(strip=True)
            if not cand or len(cand) < 6:
                continue
            if skip_title.search(cand):
                continue
            title = cand
            break
        if prev is not None and title:
            n = prev.find_next_sibling()
            while n is not None and n != a:
                if getattr(n, "name", None) == "p":
                    excerpt = n.get_text(separator=" ", strip=True)[:300]
                    break
                if getattr(n, "name", None) in ("div", "span", "section"):
                    tx = n.get_text(separator=" ", strip=True)
                    if tx and len(tx) < 55 and re.search(r"\d{4}", tx):
                        date_str = tx[:50]
                n = n.find_next_sibling()
        out.append(
            {
                "title": title or "Новина",
                "url": href,
                "date": date_str,
                "excerpt": excerpt,
                "image": "",
                "is_pinned": False,
            }
        )
        if len(out) >= 30:
            break
    return out

def parse_istu_news(page: int = 1) -> list[dict]:
    out = []
    url = NEWS_URL.rstrip("/") + ("/page/" + str(page) + "/" if page > 1 else "/")
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.find_all("article") or soup.select(".post, .type-post, [class*='post-']")
        if not articles:
            articles = soup.select("main article, .content article, .news-list article")
        if not articles and page == 1:
            for h in soup.find_all(["h2", "h3"]):
                a = h.find("a", href=True)
                if a and "istu.edu.ua" in a.get("href", ""):
                    block = h.find_parent("article") or h.find_parent("div", class_=re.compile(r"post|entry|news", re.I))
                    if block:
                        articles = [block]
                        break
            if not articles:
                links = soup.find_all("a", href=re.compile(r"istu\.edu\.ua/.*novyny|istu\.edu\.ua/[^/]+$"))
                seen = set()
                for a in links:
                    href = a.get("href", "")
                    if href in seen or "novyny" not in href and "/novyny/" not in r.url:
                        continue
                    title = (a.get_text(strip=True) or "").strip()[:200]
                    if not title or "read more" in title.lower() or "читати" in title.lower():
                        continue
                    seen.add(href)
                    if not href.startswith("http"):
                        href = urljoin(url, href)
                    out.append({"title": title, "url": href, "date": "", "excerpt": "", "image": "", "is_pinned": False})
                if out:
                    return out[:30]
        for art in articles[:30]:
            title, link_url, date_str, excerpt, img_url = "", "", "", "", ""
            class_tokens = " ".join(art.get("class", [])).lower() if hasattr(art, "get") else ""
            is_pinned = "sticky" in class_tokens or "pinned" in class_tokens or "pin" in class_tokens
            if not is_pinned:
                for pin_el in art.select(".sticky, .pinned, .pin, [class*='stick'], [class*='pin']"):
                    pin_class = " ".join(pin_el.get("class", [])).lower() if hasattr(pin_el, "get") else ""
                    if "sticky" in pin_class or "pin" in pin_class:
                        is_pinned = True
                        break
            h = art.find(["h2", "h3"])
            if h:
                a = h.find("a", href=True)
                if a:
                    title = a.get_text(strip=True)
                    link_url = a.get("href", "")
                else:
                    title = h.get_text(strip=True)
                if link_url and not link_url.startswith("http"):
                    link_url = urljoin(url, link_url)
            if not title:
                a = art.find("a", href=re.compile(r"istu\.edu\.ua"))
                if a:
                    title = a.get_text(strip=True)[:200]
                    link_url = link_url or (a.get("href") or "")
                    if link_url and not link_url.startswith("http"):
                        link_url = urljoin(url, link_url)
            time_el = art.find("time")
            if time_el and time_el.get("datetime"):
                date_str = time_el.get("datetime", "")[:10]
            if not date_str:
                for t in art.find_all(string=re.compile(r"[А-Яа-яІіЇїЄє]{3}\s+\d{1,2},\s*\d{4}|^\d{1,2}\s+[А-Яа-я]+\s+\d{4}")):
                    date_str = t.strip()[:50]
                    break
            summary = art.select_one(".entry-summary, .excerpt, .post-excerpt, [class*='summary']")
            if summary:
                excerpt = summary.get_text(separator=" ", strip=True)[:300]
            if not excerpt:
                p = art.find("p")
                if p:
                    excerpt = p.get_text(separator=" ", strip=True)[:300]
            img_el = art.select_one(".post-thumbnail img, .wp-post-image, .entry-content img, [class*='thumbnail'] img, figure img")
            if not img_el:
                img_el = art.find("img", src=True)
            if img_el and img_el.get("src"):
                img_url = img_el.get("src", "").strip()
                if img_url and not img_url.startswith("http"):
                    img_url = urljoin(url, img_url)
            if img_url and ("data:image" in img_url or "placeholder" in img_url.lower()):
                img_url = ""
            if title or excerpt:
                out.append(
                    {
                        "title": title or "Новина",
                        "url": link_url or url,
                        "date": date_str,
                        "excerpt": excerpt,
                        "image": img_url,
                        "is_pinned": bool(is_pinned),
                    }
                )
        if not out:
            out = _parse_istu_news_readmore_fallback(soup, url)
    except Exception as e:
        if page == 1:
            out = [{"title": "Помилка завантаження", "url": NEWS_URL, "date": "", "excerpt": str(e)[:200], "image": ""}]
    return out
