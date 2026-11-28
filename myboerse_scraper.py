#!/usr/bin/env python3
"""Archive MyBoerse member threads and MyGully subforums as HTML using Camoufox."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlsplit

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

BASE_HOST = "myboerse.bz"
MYGULLY_HOST = "mygully.com"
MYGULLY_SUBFORUM = re.compile(r"/forum/(\d+)(?:-[^/]+)?/?")
MYGULLY_LOGOUT = "a[href*='login.php?do=logout']"
LOG = logging.getLogger("myboerse_scraper")


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return value[:120] or "thread"


def thread_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.hostname == MYGULLY_HOST:
        thread_id = parse_qs(parsed.query).get("t", [""])[0]
        if parsed.path.endswith("/showthread.php") and re.fullmatch(r"[0-9]+", thread_id):
            return thread_id
        return None
    # XenForo thread URLs normally end in a numeric thread ID.
    path = parsed.path.rstrip("/")
    m = re.search(r"\.(\d+)$", path)
    if m and "/threads/" in path:
        return m.group(1)
    m = re.search(r"/threads/(\d+)(?:/|$)", path)
    return m.group(1) if m else None


def validate_forum_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("https", "http") or p.hostname not in (BASE_HOST, MYGULLY_HOST):
        raise ValueError(f"Only URLs on {BASE_HOST} and {MYGULLY_HOST} are supported: {url}")


async def login_mygully(page, config: dict) -> None:
    await page.goto(f"https://{MYGULLY_HOST}/", wait_until="domcontentloaded")
    logout = page.locator(MYGULLY_LOGOUT).first
    username = page.locator('input[name="vb_login_username"]').first
    await username.or_(logout).first.wait_for(state="visible")
    if await logout.count():
        LOG.info("Already logged in to MyGully.")
        return

    if not config.get("username") or not config.get("password"):
        raise RuntimeError("Config must contain non-empty 'username' and 'password'.")

    form = page.locator("form").filter(has=username).first
    action = urlsplit(urljoin(page.url, await form.get_attribute("action") or ""))
    if action.scheme != "https" or action.netloc != MYGULLY_HOST or action.path != "/login.php":
        raise RuntimeError("Unexpected MyGully login form action.")
    await username.fill(config["username"])
    await form.locator('input[name="vb_login_password"]').fill(config["password"])
    await form.locator('input[type="submit"], button[type="submit"]').first.click()
    try:
        await logout.wait_for(state="visible")
    except PlaywrightTimeoutError as exc:
        raise RuntimeError("Could not confirm MyGully login. Check the credentials and browser page.") from exc


def mygully_page_number(url: str) -> int:
    value = parse_qs(urlsplit(url).query).get("page", ["1"])[0]
    return int(value) if re.fullmatch(r"[0-9]+", value) else 1


async def mygully_next_page(page, current: str, start_url: str) -> str | None:
    start = urlsplit(start_url)
    forum = MYGULLY_SUBFORUM.fullmatch(start.path)
    forum_id = forum.group(1)
    next_number = mygully_page_number(current) + 1
    hrefs = await page.locator('a[href*="forumdisplay.php"][href*="page="]').evaluate_all(
        "(links) => links.map(link => link.href)"
    )
    for href in hrefs:
        candidate = urlsplit(href)
        if candidate.hostname != MYGULLY_HOST or candidate.scheme not in ("http", "https"):
            continue
        params = parse_qs(candidate.query, keep_blank_values=True)
        if params.get("f") != [forum_id] or mygully_page_number(href) != next_number:
            continue
        # Keep the listing's pagination parameters and the caller's filters.
        params.update(parse_qs(start.query, keep_blank_values=True))
        params["f"] = [forum_id]
        params["page"] = [str(next_number)]
        return candidate._replace(query=urlencode(params, doseq=True), fragment="").geturl()
    return None


async def mygully_thread_links(page) -> list[str]:
    titles = page.locator('a[id^="thread_title_"][href]')
    if not await titles.count():
        titles = page.locator('a[href*="showthread.php?"][href*="t="]')
    hrefs = await titles.evaluate_all("(links) => links.map(link => link.href)")
    threads = {}
    for href in hrefs:
        if urlsplit(href).hostname != MYGULLY_HOST:
            continue
        thread_id = thread_id_from_url(href)
        params = parse_qs(urlsplit(href).query)
        if thread_id and not {"goto", "p", "page"}.intersection(params):
            threads.setdefault(thread_id, href)
    return list(threads.values())


async def login_if_needed(page, config: dict) -> None:
    await page.goto("https://myboerse.bz/", wait_until="domcontentloaded")
    await page.wait_for_timeout(800)
    # A logged-in XenForo header normally has a visitor menu or account link.
    if await page.locator("a[href*='/logout']").count():
        LOG.info("Already logged in.")
        return

    username = config.get("username")
    password = config.get("password")
    if not username or not password:
        raise RuntimeError("Config must contain non-empty 'username' and 'password'.")

    await page.goto("https://myboerse.bz/login/", wait_until="domcontentloaded")
    await page.locator("input[name='login']").first.wait_for(state="visible", timeout=20_000)
    await page.locator("input[name='login']").first.fill(username)
    await page.locator("input[name='password']").first.fill(password)

    # XenForo may use a hidden token and a submit button; submit the actual form.
    form = page.locator("form").filter(has=page.locator("input[name='password']")).first
    submit = form.locator("button[type='submit'], input[type='submit']").first
    if await submit.count():
        await submit.click()
    else:
        await page.locator("input[name='password']").first.press("Enter")

    try:
        # await page.wait_for_load_state("domcontentloaded", timeout=15_000)
        await page.wait_for_load_state("domcontentloaded", timeout=60_000) # 60 seconds
    except PlaywrightTimeoutError:
        pass
    await page.wait_for_timeout(1200)

    if await page.locator("input[name='password']").count() and await page.locator("input[name='password']").first.is_visible():
        raise RuntimeError(
            "Login did not appear to succeed. Check credentials or complete any challenge "
            "in the visible browser, then rerun."
        )
    LOG.info("Login submitted; continuing with current browser session.")


async def member_search_url(page, member_url: str) -> str:
    await page.goto(member_url, wait_until="domcontentloaded")
    await page.locator("body").wait_for()
    # Prefer the forum's own link (XenForo search URLs may redirect through a saved search).
    links = page.locator("a[href*='/search/member?'][href*='content=thread']")
    if await links.count():
        return urljoin(page.url, await links.first.get_attribute("href"))

    # Fallback for the known XenForo member URL format /members/name.ID/
    m = re.search(r"/members/[^/]*\.(\d+)/?", urlparse(member_url).path)
    if not m:
        raise RuntimeError("Could not find 'all threads by this user' link or member ID in URL.")
    user_id = m.group(1)
    # Let the forum create its normal saved search via the member profile if possible.
    raise RuntimeError(
        f"Member page did not expose the expected search link. Member ID is {user_id}; "
        "inspect the current page selectors before using a hard-coded search URL."
    )


async def extract_thread_links(page) -> list[str]:
    # XenForo 2 thread list. Limit links to actual thread titles, not last-post links.
    selectors = [
        # ".structItem--thread .structItem-title a[href*='/threads/']",
        # ".structItem-title a[href*='/threads/']",
        # ".searchResult-title a[href*='/threads/']",
        "ol.block-body > li.block-row > div.contentRow > div.contentRow-main > h3.contentRow-title > a",
    ]
    for selector in selectors:
        print(f"extract_thread_links: selector={selector!r}")
        loc = page.locator(selector)
        if await loc.count():
            print(f"extract_thread_links: found {await loc.count()} elements")
            found = []
            for i in range(await loc.count()):
                href = await loc.nth(i).get_attribute("href")
                print(f"extract_thread_links: href={href!r}")
                if href:
                    full = urljoin(page.url, href)
                    if thread_id_from_url(full):
                        found.append(full)
            if found:
                return list(dict.fromkeys(found))
    return []


async def find_next_page(page) -> str | None:
    # XenForo's next-page link has rel=next on many themes; class fallback covers others.
    for selector in [
        "a.pageNav-jump--next[href]",
        "a[rel='next'][href]",
        ".pageNav a[href][aria-label*='Next']",
    ]:
        loc = page.locator(selector)
        if await loc.count():
            href = await loc.first.get_attribute("href")
            if href:
                print(f"find_next_page: found next-page link href={href!r} with selector={selector!r}")
                return urljoin(page.url, href)
    if 1:
        # debug
        # last page?
        html = await page.content()
        html_path = "find_next_page.page.content.html"
        print(f"find_next_page: writing {html_path!r}")
        with open(html_path, "w") as f:
            f.write(html)
        print(f"find_next_page: found no next-page link on page page.url={page.url!r} html_path={html_path}")
    return None


def write_thread_html(target: Path, html: str) -> None:
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(html)
            file.close()
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


async def scrape_mygully_subforum(page, start_url: str, output: Path, delay: float) -> None:
    current = start_url
    downloaded = skipped = 0
    seen_threads = set()
    while current:
        LOG.info("Subforum page: %s", current)
        response = await page.goto(current, wait_until="domcontentloaded")
        if not response or not response.ok or urlsplit(page.url).hostname != MYGULLY_HOST:
            raise RuntimeError(f"Could not open MyGully listing {current}")
        if mygully_page_number(page.url) != mygully_page_number(current):
            raise RuntimeError(f"MyGully redirected to a different listing page: {page.url}")

        thread_urls = await mygully_thread_links(page)
        if not thread_urls:
            raise RuntimeError(f"No MyGully thread links found at {page.url}")
        next_url = await mygully_next_page(page, current, start_url)

        for thread_url in thread_urls:
            thread_id = thread_id_from_url(thread_url)
            if thread_id in seen_threads:
                continue
            seen_threads.add(thread_id)
            target = output / f"{thread_id}.html"
            if target.exists():
                skipped += 1
                continue
            LOG.info("Downloading thread %s: %s", thread_id, thread_url)
            response = await page.goto(thread_url, wait_until="domcontentloaded")
            if (
                not response
                or not response.ok
                or urlsplit(page.url).hostname != MYGULLY_HOST
                or thread_id_from_url(page.url) != thread_id
                or not await page.locator("#posts").count()
            ):
                raise RuntimeError(f"Could not load MyGully thread {thread_id} at {thread_url}")
            write_thread_html(target, await page.content())
            downloaded += 1
            await asyncio.sleep(delay)

        current = next_url
        if current:
            await asyncio.sleep(delay)
    LOG.info("Finished. Downloaded %d; skipped cached %d.", downloaded, skipped)


async def scrape_member(page, member_url: str, output: Path, delay: float) -> None:
    search_url = await member_search_url(page, member_url)
    print(f"scrape_member: search_url={search_url!r}")
    seen_search_pages: set[str] = set()
    downloaded = skipped = 0
    current = search_url

    while current and current not in seen_search_pages:
        seen_search_pages.add(current)
        LOG.info("Search page: %s", current)
        await page.goto(current, wait_until="domcontentloaded")
        await page.locator("body").wait_for()
        # If the forum's search endpoint redirects, page.url is the canonical result page.
        current = page.url
        print(f"scrape_member: page.url={page.url!r}")
        thread_urls = await extract_thread_links(page)
        if not thread_urls:
            title = (await page.title()).strip()
            raise RuntimeError(
                f"No thread results found at {current!r} (page title: {title!r}). "
                "This may be a login/challenge page or the forum's HTML selectors changed."
            )

        for thread_url in thread_urls:
            tid = thread_id_from_url(thread_url)
            if not tid:
                continue
            target = output / f"{tid}.html"
            if target.exists():
                skipped += 1
                LOG.info("Cached, skipping thread %s", tid)
                continue

            LOG.info("Downloading thread %s: %s", tid, thread_url)
            await page.goto(thread_url, wait_until="domcontentloaded")
            await page.locator("body").wait_for()
            # Detect obvious auth/challenge redirects rather than caching the wrong page.
            final_url = page.url
            if "/login" in urlparse(final_url).path or await page.locator("input[name='password']").count():
                raise RuntimeError(f"Lost login session while opening {thread_url}")

            html = await page.content()
            if len(html) < 1000:
                raise RuntimeError(f"Refusing to cache suspiciously short HTML for {thread_url}")
            write_thread_html(target, html)
            downloaded += 1
            await asyncio.sleep(delay)

        # We are currently on the last thread page, so navigate back to the search page
        # before checking its pagination.
        await page.goto(current, wait_until="domcontentloaded")
        next_url = await find_next_page(page)
        if not next_url or next_url in seen_search_pages:
            break
        current = next_url
        await asyncio.sleep(delay)

    LOG.info("Finished. Downloaded %d; skipped cached %d.", downloaded, skipped)


async def async_main(args) -> int:
    config_path = Path(args.config).expanduser()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Could not read JSON config {config_path}: {exc}") from exc

    validate_forum_url(args.start_url)
    start = urlsplit(args.start_url)
    is_mygully = start.hostname == MYGULLY_HOST
    if is_mygully and not MYGULLY_SUBFORUM.fullmatch(start.path):
        raise ValueError("Use a MyGully subforum URL such as https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/")
    if not is_mygully and not start.path.startswith("/members/"):
        raise ValueError("Use a MyBoerse member profile URL.")
    default_output = "archive/mygully.com" if is_mygully else "archive/myboerse"
    output = Path(args.output or default_output).expanduser()
    output.mkdir(parents=True, exist_ok=True)

    async with AsyncCamoufox(headless=args.headless) as browser:
        context = await browser.new_context(
            accept_downloads=False,
            locale="de-DE",
            user_agent=config.get("user_agent") or None,
        )
        page = await context.new_page()
        # page.set_default_timeout(15_000) # 15 seconds
        page.set_default_timeout(60_000) # 60 seconds
        try:
            if is_mygully:
                await login_mygully(page, config)
                await scrape_mygully_subforum(page, args.start_url, output, args.delay)
            else:
                await login_if_needed(page, config)
                await scrape_member(page, args.start_url, output, args.delay)
        except Exception as exc:
            if not is_mygully and not args.headless:
                print(f"got exception: {type(exc).__name__}: {exc}")
                print("keeping browser open for debugging")
                await asyncio.sleep(99999)
            raise
        finally:
            await context.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Path to JSON credentials config")
    parser.add_argument("--start-url", required=True, help="MyBoerse member or MyGully subforum URL")
    parser.add_argument("--output", help="HTML archive directory (default: archive/myboerse or archive/mygully.com)")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between thread downloads")
    parser.add_argument("--headless", action="store_true", help="Run browser headless (default: visible)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        LOG.warning("Interrupted.")
        return 130
    except Exception as exc:
        LOG.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
