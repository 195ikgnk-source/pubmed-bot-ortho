"""
PubMed → Claude翻訳 → Discord 自動配信スクリプト
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

# ── 設定 ──────────────────────────────────────────────────────────────
KEYWORDS       = os.environ.get("PUBMED_KEYWORDS", "menopause hormone therapy")
MAX_RESULTS    = int(os.environ.get("MAX_RESULTS", "5"))
DISCORD_WEBHOOK= os.environ.get("DISCORD_WEBHOOK_URL", "")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
PUBMED_API_KEY = os.environ.get("PUBMED_API_KEY", "")   # 任意。あると制限緩和
# ──────────────────────────────────────────────────────────────────────

JST = timezone(timedelta(hours=9))
BASE_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
BASE_EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


# ── PubMed ────────────────────────────────────────────────────────────

def pubmed_search(keywords: str, max_results: int) -> list[str]:
    """過去1日以内の新着PMIDを返す"""
    params = {
        "db": "pubmed",
        "term": f"({keywords})",
        "reldate": "1",          # 過去1日
        "datetype": "edat",
        "retmax": str(max_results),
        "retmode": "json",
        "sort": "date",
    }
    if PUBMED_API_KEY:
        params["api_key"] = PUBMED_API_KEY

    url = BASE_ESEARCH + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read())
    return data.get("esearchresult", {}).get("idlist", [])


def pubmed_fetch(pmids: list[str]) -> list[dict]:
    """PMIDリストからタイトル・アブストラクト・著者・雑誌を取得"""
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        "rettype": "abstract",
    }
    if PUBMED_API_KEY:
        params["api_key"] = PUBMED_API_KEY

    url = BASE_EFETCH + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.loads(r.read())

    articles = []
    for pmid, art in data.get("PubmedArticleSet", {}).get("PubmedArticle", {}).items() \
            if isinstance(data.get("PubmedArticleSet", {}).get("PubmedArticle"), dict) \
            else enumerate(data.get("PubmedArticleSet", {}).get("PubmedArticle", [])):

        medline = art.get("MedlineCitation", {})
        article = medline.get("Article", {})

        title = article.get("ArticleTitle", "")
        if isinstance(title, dict):
            title = title.get("#text", "")

        abstract_raw = article.get("Abstract", {}).get("AbstractText", "")
        if isinstance(abstract_raw, list):
            abstract = " ".join(
                (x.get("#text", x) if isinstance(x, dict) else str(x))
                for x in abstract_raw
            )
        elif isinstance(abstract_raw, dict):
            abstract = abstract_raw.get("#text", "")
        else:
            abstract = str(abstract_raw)

        journal = article.get("Journal", {}).get("Title", "")
        pub_year = (
            article.get("Journal", {})
            .get("JournalIssue", {})
            .get("PubDate", {})
            .get("Year", "")
        )

        authors_raw = article.get("AuthorList", {}).get("Author", [])
        if isinstance(authors_raw, dict):
            authors_raw = [authors_raw]
        authors = []
        for a in authors_raw[:3]:
            ln = a.get("LastName", "")
            fn = a.get("ForeName", "")
            if ln:
                authors.append(f"{ln} {fn}".strip())
        author_str = ", ".join(authors) + (" et al." if len(authors_raw) > 3 else "")

        articles.append({
            "pmid": pmids[pmid] if isinstance(pmid, int) else pmid,
            "title": title,
            "abstract": abstract[:1500],   # Claude APIへ送る上限
            "journal": journal,
            "year": pub_year,
            "authors": author_str,
        })
    return articles


# ── Claude API ────────────────────────────────────────────────────────

def translate_article(article: dict) -> dict:
    """タイトルとアブストラクトを日本語に翻訳・要約する"""
    prompt = f"""以下の医学論文を日本語で簡潔に要約してください。

## タイトル
{article['title']}

## アブストラクト
{article['abstract']}

## 出力形式（JSON のみ返答。余計な文は不要）
{{
  "title_ja": "日本語タイトル",
  "summary_ja": "アブストラクトの日本語要約（150〜200字程度）"
}}"""

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())

    raw = resp["content"][0]["text"].strip()
    # JSON フェンスを除去
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    translated = json.loads(raw)
    article.update(translated)
    return article


# ── Discord ───────────────────────────────────────────────────────────

def build_discord_payload(articles: list[dict], keywords: str) -> dict:
    now_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    embeds = []

    for art in articles:
        pmid = art["pmid"]
        title_ja = art.get("title_ja", art["title"])
        summary_ja = art.get("summary_ja", "（要約なし）")
        journal = art.get("journal", "")
        year = art.get("year", "")
        authors = art.get("authors", "")
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

        meta_parts = [x for x in [authors, journal, year] if x]
        meta = " · ".join(meta_parts)

        embeds.append({
            "title": title_ja,
            "url": pubmed_url,
            "description": summary_ja,
            "color": 5793266,   # #587BF2 Discord blue
            "footer": {"text": f"PMID: {pmid}  {meta}"},
        })

    return {
        "username": "PubMed Bot",
        "content": f"📚 **新着論文** — `{keywords}` ({now_jst})  {len(articles)}件",
        "embeds": embeds[:10],  # Discord上限
    }


def post_to_discord(payload: dict) -> None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        DISCORD_WEBHOOK,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        status = r.status
    print(f"Discord: HTTP {status}")


# ── メイン ────────────────────────────────────────────────────────────

def main():
    if not DISCORD_WEBHOOK:
        sys.exit("ERROR: DISCORD_WEBHOOK_URL が設定されていません")
    if not ANTHROPIC_KEY:
        sys.exit("ERROR: ANTHROPIC_API_KEY が設定されていません")

    print(f"[{datetime.now(JST).strftime('%H:%M JST')}] 検索キーワード: {KEYWORDS}")

    pmids = pubmed_search(KEYWORDS, MAX_RESULTS)
    print(f"PubMed: {len(pmids)} 件ヒット → {pmids}")

    if not pmids:
        print("新着論文なし。Discordへの投稿をスキップします。")
        return

    articles = pubmed_fetch(pmids)
    print(f"取得: {len(articles)} 件")

    translated = []
    for art in articles:
        try:
            translated.append(translate_article(art))
            time.sleep(0.5)   # API レート制限対策
        except Exception as e:
            print(f"翻訳エラー (PMID {art['pmid']}): {e}")
            translated.append(art)   # 翻訳失敗時は原文で投稿

    payload = build_discord_payload(translated, KEYWORDS)
    post_to_discord(payload)
    print("完了")


if __name__ == "__main__":
    main()
