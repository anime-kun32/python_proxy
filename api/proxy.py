import os
import httpx
from urllib.parse import urljoin, quote

BLOG_HOST = os.getenv("BLOG_HOST", "megacloud.blog")
FIXED_BLOG_REFERER = f"https://{BLOG_HOST}/"
FIXED_BLOG_ORIGIN = f"https://{BLOG_HOST}"


def rewrite_m3u8_playlist(text: str, base_url: str):
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#") or line == "":
            lines.append(line)
            continue

        abs_url = urljoin(base_url, line)
        proxy_url = f"/api/proxy?url={quote(abs_url)}"
        lines.append(proxy_url)

    return "\n".join(lines)


async def handler(request):
    # Vercel entry point
    url = request.query.get("url")
    if not url:
        return {
            "status": 400,
            "headers": {"Content-Type": "application/json"},
            "body": '{"error":"Missing url"}'
        }

    headers = {
        "User-Agent": request.headers.get(
            "user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        ),
        "Accept": "*/*",
        "Referer": FIXED_BLOG_REFERER,
        "Origin": FIXED_BLOG_ORIGIN,
    }

    # Include Range header for TS segments
    if "range" in request.headers:
        headers["Range"] = request.headers["range"]

    async with httpx.AsyncClient(follow_redirects=True) as client:
        r = await client.get(url, headers=headers)

    content_type = r.headers.get("content-type", "")

    # ----------------------------------------
    # Playlist (#EXTM3U)
    # ----------------------------------------
    if "mpegurl" in content_type or url.endswith(".m3u8"):
        rewritten = rewrite_m3u8_playlist(r.text, url)

        return {
            "status": r.status_code,
            "headers": {
                "Content-Type": "application/vnd.apple.mpegurl",
                "Cache-Control": "no-store",
                "Access-Control-Allow-Origin": "*",
            },
            "body": rewritten
        }

    # ----------------------------------------
    # TS / binary chunks (Serverless must buffer)
    # ----------------------------------------
    return {
        "status": r.status_code,
        "headers": {
            "Content-Type": content_type or "video/MP2T",
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        },
        "body": r.content
    }
