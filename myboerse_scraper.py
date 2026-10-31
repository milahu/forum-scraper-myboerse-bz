#!/usr/bin/env python3
"""Archive MyBoerse member-created threads as HTML, using Patchright."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

from patchright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

BASE_HOST = "myboerse.bz"
LOG = logging.getLogger("myboerse_scraper")


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return value[:120] or "thread"


def thread_id_from_url(url: str) -> str | None:
    # XenForo thread URLs normally end in a numeric thread ID.
    path = urlparse(url).path.rstrip("/")
    m = re.search(r"\.(\d+)$", path)
    if m and "/threads/" in path:
        return m.group(1)
    m = re.search(r"/threads/(\d+)(?:/|$)", path)
    return m.group(1) if m else None


def validate_forum_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("https", "http") or p.hostname != BASE_HOST:
        raise ValueError(f"Only URLs on https://{BASE_HOST}/ are supported: {url}")


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
    await page.locator("input[name='login']").first.wait_for(state="visible", timeout=20000)
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
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
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
        ".structItem--thread .structItem-title a[href*='/threads/']",
        ".structItem-title a[href*='/threads/']",
        ".searchResult-title a[href*='/threads/']",
    ]
    for selector in selectors:
        loc = page.locator(selector)
        if await loc.count():
            found = []
            for i in range(await loc.count()):
                href = await loc.nth(i).get_attribute("href")
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
                return urljoin(page.url, href)
    return None


async def scrape_member(page, member_url: str, output: Path, delay: float) -> None:
    search_url = await member_search_url(page, member_url)
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
            # Atomic write: interrupted runs won't leave a partial file that looks cached.
            tmp = target.with_suffix(".html.tmp")
            tmp.write_text(html, encoding="utf-8")
            tmp.replace(target)
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
    output = Path(args.output).expanduser()
    output.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        context = await browser.new_context(
            accept_downloads=False,
            locale="de-DE",
            user_agent=config.get("user_agent") or None,
        )
        page = await context.new_page()
        page.set_default_timeout(15000)
        try:
            await login_if_needed(page, config)
            path = urlparse(args.start_url).path
            if path.startswith("/members/"):
                await scrape_member(page, args.start_url, output, args.delay)
            else:
                raise NotImplementedError(
                    "This first version implements member URLs only. Other start URL types "
                    "are intentionally reserved for future handlers."
                )
        finally:
            await context.close()
            await browser.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Path to JSON credentials config")
    parser.add_argument("--start-url", required=True, help="Forum member URL to archive")
    parser.add_argument("--output", default="archive/myboerse", help="HTML archive directory")
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
