import os
import httpx
from urllib.parse import urljoin, quote

BLOG_HOST = os.getenv("BLOG_HOST", "megacloud.blog")
FIXED_BLOG_REFERER = f"https://{BLOG_HOST}/"
FIXED_BLOG_ORIGIN = f"https://{BLOG_HOST}"


def log(*args):
    # Force flush for Vercel
    print("[proxy-debug]", *args, flush=True)


def rewrite_m3u8_playlist(text: str, base_url: str):
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#") or line == "":
            lines.append(line)
            continue

        try:
            abs_url = urljoin(base_url, line)
            proxy_url = f"/api/proxy?url={quote(abs_url)}"
            lines.append(proxy_url)
        except Exception as e:
            log("Rewrite error:", e)
            lines.append(line)

    return "\n".join(lines)


async def handler(request):
    try:
        log("🔵 Handler called")
        log("Query:", request.query)
        log("Headers:", dict(request.headers))
    except Exception as e:
        print("[proxy-debug] Request introspection failed:", e)

    # -------------------------------------------------------
    # Parse URL
    # -------------------------------------------------------
    url = request.query.get("url")
    if not url:
        log("❌ Missing url param")
        return {
            "status": 400,
            "headers": {"Content-Type": "application/json"},
            "body": '{"error":"Missing url"}'
        }

    log("🔗 Target URL:", url)

    # -------------------------------------------------------
    # Build headers
    # -------------------------------------------------------
    try:
        headers = {
            "User-Agent": request.headers.get(
                "user-agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            ),
            "Accept": "*/*",
            "Referer": FIXED_BLOG_REFERER,
            "Origin": FIXED_BLOG_ORIGIN,
        }

        if "range" in request.headers:
            headers["Range"] = request.headers["range"]

        log("📦 Outgoing headers:", headers)
    except Exception as e:
        log("❌ Header build failed:", e)

    # -------------------------------------------------------
    # Fetch using httpx
    # -------------------------------------------------------
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            log("🌍 Sending request...")
            r = await client.get(url, headers=headers)
            log("🌍 Upstream status:", r.status_code)
            log("🌍 Upstream headers:", dict(r.headers))
    except Exception as e:
        log("🔥 HTTPX REQUEST FAILED:", repr(e))
        return {
            "status": 500,
            "headers": {"Content-Type": "application/json"},
            "body": f'{{"error":"httpx failed","details":"{repr(e)}"}}'
        }

    # -------------------------------------------------------
    # Check content type
    # -------------------------------------------------------
    content_type = r.headers.get("content-type", "")
    log("📺 Content-Type:", content_type)

    # -------------------------------------------------------
    # Handle playlist
    # -------------------------------------------------------
    try:
        if "mpegurl" in content_type or url.endswith(".m3u8"):
            log("📄 Playlist detected. Rewriting...")
            rewritten = rewrite_m3u8_playlist(r.text, url)
            log("📄 Playlist rewrite complete.")
            return {
                "status": r.status_code,
                "headers": {
                    "Content-Type": "application/vnd.apple.mpegurl",
                    "Cache-Control": "no-store",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": rewritten
            }
    except Exception as e:
        log("❌ Playlist handling error:", e)

    # -------------------------------------------------------
    # TS / Binary
    # -------------------------------------------------------
    try:
        log("📦 Binary response. Length:", len(r.content))
        return {
            "status": r.status_code,
            "headers": {
                "Content-Type": content_type or "video/MP2T",
                "Cache-Control": "no-store",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*"
            },
            "body": r.content
        }
    except Exception as e:
        log("🔥 FINAL PIPE ERROR:", e)
        return {
            "status": 500,
            "headers": {"Content-Type": "application/json"},
            "body": f'{{"error":"final send failed","details":"{repr(e)}"}}'
        }
