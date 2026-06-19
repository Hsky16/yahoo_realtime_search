from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP

API_URL = "https://search.yahoo.co.jp/realtime/api/v1/pagination"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

Sort = Literal["latest", "popular"]
MediaType = Literal["all", "image", "video"]
OutputFormat = Literal["markdown", "compact_json", "full_json", "raw_json"]

SERVER_INSTRUCTIONS = """
この MCP は Yahoo!リアルタイム検索を呼び出します。主に最近の公開 X/Twitter 投稿、
投稿への反応、画像や動画付き投稿を調べるためのものです。

現在の話題への反応、速報的な盛り上がり、ハッシュタグ、アカウント指定検索、
日本語圏の話題、最近の投稿例、画像や動画付き投稿を探したいときに使ってください。

一般的な Web 検索、公式情報の確認、ドキュメント調査、長文記事の検索、
恒久的な事実確認には向きません。その場合は通常の Web 検索や公式情報を使ってください。

標準の Markdown 出力は、投稿ごとの JSON キーの繰り返しを避け、エージェントが読みやすい
形にしています。構造化データが必要なときだけ compact_json、より詳しい整形済みデータが
必要なときは full_json、API レスポンスの確認やデバッグには raw_json を使ってください。
"""

mcp = FastMCP("yahoo_realtime_search", instructions=SERVER_INSTRUCTIONS)


def _to_unix_timestamp(value: int | float | str | None) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)

    text = value.strip()
    if text.isdigit():
        return int(text)

    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Invalid datetime: {value!r}. Use Unix seconds or ISO 8601, "
            "for example 2026-01-01T00:00:00+09:00."
        ) from exc

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _build_params(
    *,
    query: str,
    sort: Sort = "latest",
    media_type: MediaType = "image",
    results: int = 40,
    start: int | None = None,
    oldest_tweet_id: str | None = None,
    since: int | float | str | None = None,
    until: int | float | str | None = None,
) -> dict[str, str]:
    if not query or not query.strip():
        raise ValueError("query is required.")
    if not 1 <= results <= 40:
        raise ValueError("results must be between 1 and 40.")
    if start is not None and not 1 <= start <= 10_000:
        raise ValueError("start must be between 1 and 10000.")

    params = {
        "p": query.strip(),
        "results": str(results),
    }
    if sort == "popular":
        params["md"] = "h"
    if media_type != "all":
        params["mtype"] = media_type
    if start is not None:
        params["start"] = str(start)
    if oldest_tweet_id:
        params["oldestTweetId"] = oldest_tweet_id

    since_ts = _to_unix_timestamp(since)
    until_ts = _to_unix_timestamp(until)
    if since_ts is not None:
        params["since"] = str(since_ts)
    if until_ts is not None:
        params["until"] = str(until_ts)
    return params


async def _fetch_page(params: dict[str, str]) -> dict[str, Any]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://search.yahoo.co.jp/realtime/search",
    }
    async with httpx.AsyncClient(headers=headers, timeout=20.0) as client:
        response = await client.get(API_URL, params=params)
        response.raise_for_status()
        return response.json()


def _extract_media(entry: dict[str, Any]) -> list[dict[str, Any]]:
    media_items = []
    for media in entry.get("media") or []:
        item = media.get("item") or {}
        media_items.append(
            {
                "type": media.get("type"),
                "media_url": item.get("mediaUrl"),
                "thumbnail_url": item.get("thumbnailImageUrl") or media.get("metaImageUrl"),
                "display_url": item.get("displayUrl"),
                "duration_ms": item.get("duration"),
                "width": (item.get("sizes") or {}).get("viewer", {}).get("width"),
                "height": (item.get("sizes") or {}).get("viewer", {}).get("height"),
                "source_url": item.get("url"),
            }
        )
    return media_items


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    created_at = entry.get("createdAt")
    created_at_iso = None
    if isinstance(created_at, int):
        created_at_iso = datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat()

    return {
        "id": entry.get("id"),
        "url": entry.get("url"),
        "text": entry.get("displayTextBody") or entry.get("displayText"),
        "created_at": created_at,
        "created_at_iso": created_at_iso,
        "user": {
            "id": entry.get("userId"),
            "name": entry.get("name"),
            "screen_name": entry.get("screenName"),
            "url": entry.get("userUrl"),
            "profile_image": entry.get("profileImage"),
            "badge": entry.get("badge"),
        },
        "counts": {
            "replies": entry.get("replyCount"),
            "reposts": entry.get("rtCount"),
            "quotes": entry.get("qtCount"),
            "likes": entry.get("likesCount"),
        },
        "hashtags": [tag.get("text") for tag in entry.get("hashtags") or []],
        "mentions": entry.get("mentions") or [],
        "urls": entry.get("urls") or [],
        "media_types": entry.get("mediaType") or [],
        "media": _extract_media(entry),
        "possibly_sensitive": entry.get("possiblySensitive"),
        "quoted_tweet": entry.get("quotedTweet"),
        "in_reply_to": entry.get("inReplyTo"),
    }


def _normalize_response(data: dict[str, Any]) -> dict[str, Any]:
    timeline = data.get("timeline") or {}
    entries = timeline.get("entry") or []
    return {
        "head": timeline.get("head") or {},
        "media_tweet": timeline.get("mediaTweet"),
        "count": len(entries),
        "next_oldest_tweet_id": entries[-1].get("id") if entries else None,
        "entries": [_normalize_entry(entry) for entry in entries],
    }


def _first_link_title(entry: dict[str, Any]) -> str | None:
    for link in entry.get("urls") or []:
        if link.get("title"):
            return link["title"]
    return None


def _compact_entry(entry: dict[str, Any]) -> dict[str, Any]:
    media = _extract_media(entry)
    links = [
        {
            "title": link.get("title"),
            "url": link.get("expandedUrl") or link.get("url"),
            "display_url": link.get("displayUrl"),
        }
        for link in entry.get("urls") or []
    ]
    return {
        "id": entry.get("id"),
        "title": _first_link_title(entry),
        "text": entry.get("displayTextBody") or entry.get("displayText"),
        "url": entry.get("url"),
        "author": f"{entry.get('name')} (@{entry.get('screenName')})",
        "created_at": entry.get("createdAt"),
        "metrics": {
            "likes": entry.get("likesCount"),
            "reposts": entry.get("rtCount"),
            "replies": entry.get("replyCount"),
            "quotes": entry.get("qtCount"),
        },
        "hashtags": [tag.get("text") for tag in entry.get("hashtags") or []],
        "links": [link for link in links if link["url"]],
        "media": [item for item in media if item["media_url"] or item["thumbnail_url"]],
    }


def _format_count(value: Any) -> str:
    if not isinstance(value, int):
        return "-"
    if value >= 10_000:
        return f"{value / 10_000:.1f}万"
    return str(value)


def _entry_to_markdown(index: int, entry: dict[str, Any]) -> str:
    compact = _compact_entry(entry)
    text = " ".join(str(compact["text"] or "").split())
    if len(text) > 220:
        text = f"{text[:217]}..."
    created_at = compact["created_at"]
    created_at_text = str(created_at) if created_at is not None else "-"
    if isinstance(created_at, int):
        created_at_text = datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat()

    metrics = compact["metrics"]
    media_urls = [
        item["media_url"] or item["thumbnail_url"]
        for item in compact["media"]
        if item["media_url"] or item["thumbnail_url"]
    ]
    links = [link for link in compact["links"] if link.get("url")]
    lines = [
        (
            f"### {index}. {compact['author']} | {created_at_text} | "
            f"likes {_format_count(metrics['likes'])}, "
            f"reposts {_format_count(metrics['reposts'])}, "
            f"replies {_format_count(metrics['replies'])}, "
            f"quotes {_format_count(metrics['quotes'])} | "
            f"[post]({compact['url']})"
        )
    ]
    if text:
        lines.append(f"> {text}")
    if links:
        lines.extend(_format_markdown_link(link) for link in links[:3])
    if media_urls:
        lines.extend(f"- {url}" for url in media_urls[:3])
    return "\n".join(lines)


def _format_markdown_link(link: dict[str, Any]) -> str:
    url = link["url"]
    title = " ".join(str(link.get("title") or link.get("display_url") or url).split())
    title = title.replace("[", "\\[").replace("]", "\\]")
    return f"- [{title}]({url})"


def _entries_to_markdown(
    *,
    query: str,
    sort: Sort,
    media_type: MediaType,
    pages: int,
    entries: list[dict[str, Any]],
    total_available: Any,
) -> str:
    lines = [
        f"# Yahoo!リアルタイム検索: {query}",
        "",
        f"- 件数: {len(entries)} / 推定総件数: {total_available if total_available is not None else '-'}",
        f"- 条件: sort={sort}, media_type={media_type}, pages={pages}",
        "",
    ]
    lines.append("\n\n".join(_entry_to_markdown(i, entry) for i, entry in enumerate(entries, start=1)))
    return "\n".join(lines)


async def _fetch_pages(
    *,
    query: str,
    sort: Sort,
    media_type: MediaType,
    limit: int,
    pages: int,
    start: int,
    oldest_tweet_id: str | None,
    since: int | float | str | None,
    until: int | float | str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    if not 1 <= pages <= 25:
        raise ValueError("pages must be between 1 and 25.")
    if not 1 <= limit <= 40:
        raise ValueError("limit must be between 1 and 40.")

    starts = [start + i * limit for i in range(pages)]
    params_list = [
        _build_params(
            query=query,
            sort=sort,
            media_type=media_type,
            results=limit,
            start=None if pages == 1 and start == 1 else start_value,
            oldest_tweet_id=oldest_tweet_id if pages == 1 else None,
            since=since,
            until=until,
        )
        for start_value in starts
    ]
    page_data = await asyncio.gather(*[_fetch_page(params) for params in params_list])

    entries_by_id: dict[str, dict[str, Any]] = {}
    for page in page_data:
        for entry in (page.get("timeline") or {}).get("entry") or []:
            entry_id = entry.get("id")
            if entry_id and entry_id not in entries_by_id:
                entries_by_id[entry_id] = entry
    return page_data, list(entries_by_id.values()), params_list[0]


@mcp.tool()
async def search_realtime(
    query: str,
    sort: Sort = "latest",
    media_type: MediaType = "image",
    limit: int = 20,
    pages: int = 1,
    start: int = 1,
    oldest_tweet_id: str | None = None,
    since: int | float | str | None = None,
    until: int | float | str | None = None,
    output_format: OutputFormat = "markdown",
) -> str | dict[str, Any]:
    """Yahoo!リアルタイム検索で最近の公開投稿を検索します。

    現在の反応、トレンド、ハッシュタグ、アカウント指定検索、日本語圏の話題、
    画像や動画付き投稿を探すときに使います。一般的な Web 検索や公式情報の確認には
    使わないでください。

    主な引数:
    - query: 検索語です。"#hashtag", "-word", "A OR B", "ID:username",
      "@username", "URL:domain" などの検索演算子も使えます。
    - sort: "latest" は新着順、"popular" は反応が多い投稿を優先します。
    - media_type: "image", "video", "all" を指定できます。標準は "image" です。
    - limit: 1 ページあたりの件数です。1 から 40 まで指定できます。
    - pages: 取得するページ数です。1 から 25 まで指定できます。ページ数が増えるほど
      API へのリクエストも増えます。
    - start: 取得開始位置です。
    - since / until: Unix 秒、または ISO 8601 形式の日時を指定できます。
    - output_format: 標準は "markdown" です。構造化データが必要なときは
      "compact_json"、詳しい整形済みデータが必要なときは "full_json"、元 API の
      レスポンス確認には "raw_json" を使います。

    Markdown 出力の構造:
    - H1 に検索語を表示します。
    - 先頭の箇条書きに取得件数、推定総件数、検索条件を表示します。
    - 投稿ごとに H3 を作り、著者、ISO 形式の投稿時刻、反応数、投稿リンクを表示します。
    - 投稿本文は Yahoo 側の displayTextBody/displayText 由来で、引用として表示します。
    - 外部リンクは Markdown の箇条書きで表示します。タイトルがある場合は [title](url)、
      ない場合は display URL または URL を使います。
    - メディア URL はラベルを繰り返さず、通常の箇条書きで表示します。
    """
    page_data, entries, first_params = await _fetch_pages(
        query=query,
        sort=sort,
        media_type=media_type,
        limit=limit,
        pages=pages,
        start=start,
        oldest_tweet_id=oldest_tweet_id,
        since=since,
        until=until,
    )

    if output_format == "raw_json":
        return page_data[0] if pages == 1 else {"pages": page_data}

    total_available = ((page_data[0].get("timeline") or {}).get("head") or {}).get(
        "totalResultsAvailable"
    )
    if output_format == "markdown":
        return _entries_to_markdown(
            query=query,
            sort=sort,
            media_type=media_type,
            pages=pages,
            entries=entries,
            total_available=total_available,
        )

    if output_format == "compact_json":
        return {
            "query": query,
            "count": len(entries),
            "total_available": total_available,
            "params": first_params,
            "entries": [_compact_entry(entry) for entry in entries],
        }

    normalized_entries = [_normalize_entry(entry) for entry in entries]
    return {
        "query": query,
        "count": len(normalized_entries),
        "total_available": total_available,
        "params": first_params,
        "entries": normalized_entries,
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
