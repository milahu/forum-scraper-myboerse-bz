# Integrate Python Scripts

**User:** Anonymous  
**Created:** 2026/11/10 21:21:41  
**Updated:** 2026/11/11 19:39:06  
**Exported:** 2026/11/12 0:30:51  
**Link:** [<https://chatgpt.com/c/6af37cd4-80a0-83ed-bd9d-fc7487060813>](https://chatgpt.com/c/6af37cd4-80a0-83ed-bd9d-fc7487060813)

## Prompt:

11/10/2026, 9:31:06 PM

help me integrate two python scripts: myboerse_release_importer.py and filecrypt_scraper.py

currently i am using `myboerse_release_importer.py` to add download links to pyload, but all these links are filecrypt.cc container links and pyload fails to decrypt these filecrypt.cc container links, so before adding the download links to pyload, i want to decrypt the filecrypt.cc container links to extract the actual download links and then add the actual download links to pyload

i have created a filecrypt scraper `filecrypt_scraper.py`, which is based on a headless firefox browser controlled with the camoufox library, which i am using successfully to decrypt filecrypt.cc container links

decrypting filecrypt.cc container links is a rather expensive operation, so the decrypted urls should be cached (probably to a sqlite database) as soon as possible, so the same filecrypt.cc container link is not decrypted multiple times in future runs

also starting the firefox browser (and creating a `page` object with `page = context.new_page()`) is an expensive operation, so there should be only one browser `context` and only one browser `page` which is re-used to decrypt all container links. (we may need to change this in the future to avoid anti-bot measures...)

also each decrypted filecrypt.cc container should be added to pyload only once, using the package name from myboerse_release_importer.py and the decrypted links from filecrypt_scraper.py

in general, the script should be implemented in a "streaming" fashion, so each decrypted filecrypt.cc container is added to pyload as soon as possible

myboerse_release_importer.py

``` python
#!/usr/bin/env python3

"""
Parse archived MyBoerse release threads and optionally submit Filecrypt links to pyLoad.

It recursively parses `*.html` files,
extracts the first bold/strong release title from `.message-body .bbWrapper`,
falls back to the `<title>` prefix before `| MyBoerse.bz`,
extracts all Filecrypt Container links,
and parses release metadata with GuessIt.
Add custom rules in `filter_releases(releases, args)`.

Each release becomes one pyLoad package named after the parsed title.
Successfully accepted submissions are appended to JSONL history;
matching releases are skipped on later runs.
Failed submissions are not logged and will be retried.
The history confirms pyLoad accepted the handler request, not that the downloads completed.
Review candidates with `--dry-run` before submitting.
"""

from __future__ import annotations
import argparse, hashlib, json, logging, re, sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from guessit import guessit

LOG = logging.getLogger("myboerse_release_importer")
FILECRYPT_HOSTS = {"filecrypt.cc", "www.filecrypt.cc"}

@dataclass
class Release:
    source_file: str
    title: str
    title_source: str
    filecrypt_links: list[str]
    guessit: dict[str, Any] = field(default_factory=dict)
    @property
    def key(self) -> str:
        title = re.sub(r"\s+", " ", self.title).strip().casefold()
        material = title + "\n" + "\n".join(sorted(set(self.filecrypt_links)))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()
    @property
    def package_name(self) -> str:
        return self.title.strip()

def clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n|")

def is_filecrypt_container(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in {"http", "https"} and (p.hostname or "").lower() in FILECRYPT_HOSTS and "/container/" in p.path.lower()

def extract_release_title(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    # TODO use only the first article element
    # #js-post-5913241 > div > div.message-cell.message-cell--main > div > div > div > article > div:nth-child(1) > div
    # //*[@id="js-post-5913241"]/div/div[2]/div/div/div/article/div[1]/div
    # /html/body/div[1]/div[4]/div/div[4]/div[2]/div/div[3]/div[3]/div/div[1]/div/article/div/div[2]/div/div/div/article/div[1]/div
    # container of articles:
    # /html/body/div[1]/div[4]/div/div[4]/div[2]/div/div[3]/div[3]/div
    # <div class="p-body-content"
    #  <div class="p-body-pageContent"
    #   <div class="block block--messages"
    #    <div class="block-container lbContainer"
    #     <div class="block-body js-replyNewMessageContainer">
    # article:
    # <article class="message message--post js-post js-inlineModContainer  " id="js-post-5913241"
    #  <div class="message-inner"
    #   <div class="message-cell message-cell--main"
    #    <div class="message-main js-quickEditTarget"
    #     <div class="message-content js-messageContent"
    #      <div class="message-userContent lbContainer js-lbContainer "
    #       <article class="message-body js-selectToQuote"
    #        <div>
    #         <div class="bbWrapper"
    # article.message#js-post-5913241 > div > div.message-cell.message-cell--main > div > div > div > article > div:nth-child(1) > div

    # div.block-body > article.message:nth-child(1)
    # div.block-body > article.message:nth-child(1) > div.message-inner > div.message-cell > div.message-main > div.message-content > div.message-userContent > article.message-body > div:nth-child(1) > div.bbWrapper
    # for article in soup.select("article.message-body.js-selectToQuote, article.message-body"):
    #     wrapper = article.select_one(".bbWrapper")

    # for wrapper in soup.select("div.block-body > article.message:nth-child(1) > div.message-inner > div.message-cell > div.message-main > div.message-content > div.message-userContent > article.message-body > div:nth-child(1) > div.bbWrapper"):
    #     if not wrapper: continue
    #     print(f"wrapper={wrapper}")
    #     for node in wrapper.select("b, strong"):
    #         # print(f"extract_release_title: node.get_text: " + repr(node.get_text(" ", strip=True)))
    #         candidate = clean_title(node.get_text(" ", strip=True))
    #         if candidate and len(candidate) >= 3 and not re.search(r"^(?:download|screenshots?|nfo|mediainfo|passwort|password)\s*:?$", candidate, re.I):
    #             return candidate, "message-bold"

    # for node in soup.select("div.block-body > article.message:nth-child(1) > div.message-inner > div.message-cell > div.message-main > div.message-content > div.message-userContent > article.message-body > div:nth-child(1) > div.bbWrapper > *:nth-child(1)"):
    for node in soup.select("div.block-body > article.message:nth-child(1) > div.message-inner > div.message-cell > div.message-main > div.message-content > div.message-userContent > article.message-body > div:nth-child(1) > div.bbWrapper b:nth-child(1)"):
        # print(f"extract_release_title: node.name={node.name}")
        # print(f"extract_release_title: node:\n{node}")
        if node.name not in ("b", "strong"): continue
        # print(f"extract_release_title: node.get_text: " + repr(node.get_text(" ", strip=True)))
        candidate = clean_title(node.get_text(" ", strip=True))
        # print(f"extract_release_title: candidate={candidate!r}")
        if candidate and len(candidate) >= 3 and not re.search(r"^(?:download|screenshots?|nfo|mediainfo|passwort|password)\s*:?$", candidate, re.I):
            return candidate, "message-bold"

    # <h1 class="p-title-value">Some Title</h1>
    h1_tag = soup.select_one("h1.p-title-value")
    if h1_tag:
        # print(f"extract_release_title: h1_tag={h1_tag}")
        candidate = clean_title(h1_tag.get_text(" ", strip=True))
        # print(f"extract_release_title: candidate={candidate!r}")
        if candidate: return candidate, "page-h1"
    # else:
    #     print(f"extract_release_title: no h1_tag")

    title_tag = soup.find("title")
    if title_tag:
        full = clean_title(title_tag.get_text(" ", strip=True))
        candidate = clean_title(re.split(r"\s*\|\s*MyBoerse\.bz\b", full, maxsplit=1, flags=re.I)[0])
        # print(f"extract_release_title: candidate={candidate!r}")
        if candidate: return candidate, "page-title"
    return None, None

def extract_filecrypt_links(soup: BeautifulSoup) -> list[str]:
    links = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if is_filecrypt_container(href) and href not in links: links.append(href)
    return links

def parse_html_file(path: Path) -> Release | None:
    # print(f"parse_html_file: path={path!r}")
    try: html = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        LOG.exception("Cannot read %s", path); return None
    soup = BeautifulSoup(html, "html.parser")
    title, source = extract_release_title(soup)
    if title == "bitte löschen": return None
    # print(f"parse_html_file: title={title!r}, source={source!r}")
    links = extract_filecrypt_links(soup)
    if not title:
        LOG.warning("No release title found in %s", path); return None
    if not links:
        LOG.debug("No Filecrypt container link in %s", path); return None
    try: parsed = guessit(title); guessit_data = {str(k): str(v) for k, v in parsed.items()}
    except Exception:
        LOG.exception("GuessIt failed for %r", title); guessit_data = {}
    # print(f"parse_html_file: title={title!r}")
    print(f"parse_html_file: path={path} title={title!r}")
    return Release(str(path), title, source or "unknown", links, guessit_data)

def parse_archive(root: Path) -> list[Release]:
    releases = []

    debug_stop_after_n_releases = None
    # debug_stop_after_n_releases = 10
    n = 0

    paths = sorted(root.rglob("*.html"))
    # paths = [Path("archive/myboerse/1636873.html")] # debug: "bitte löschen"
    # paths = [Path("archive/myboerse/2868879.html")] # debug: "Haunted.Hotel.S02.GERMAN.AAC.720p.WEB.x265-w00t"

    for path in paths:
        release = parse_html_file(path)
        if release: releases.append(release)
        if debug_stop_after_n_releases and release:
            n += 1
            if n > debug_stop_after_n_releases:
                break
    return releases

def load_history(path: Path) -> dict[str, dict[str, Any]]:
    history = {}
    if not path.exists(): return history
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip(): continue
            try:
                item = json.loads(line)
                if item.get("key"): history[item["key"]] = item
            except json.JSONDecodeError: LOG.warning("Ignoring malformed history line %d", n)
    return history

def append_history(path: Path, release: Release, response: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"key": release.key, "title": release.title, "source_file": release.source_file,
              "filecrypt_links": release.filecrypt_links, "pyload_response": response,
              "added_at": datetime.now(timezone.utc).isoformat()}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()

def submit_links_to_pyload(links: Sequence[str], package: str, *, base_url: str = "http://localhost:9666",
                           passwords: str | None = None, timeout: float = 15) -> str:
    clean_links = [x.strip() for x in links if x and x.strip()]
    if not clean_links: raise ValueError("links must contain at least one URL")
    data = {"urls": "\n".join(clean_links), "package": package.strip()}
    if passwords: data["passwords"] = passwords
    response = requests.post(base_url.rstrip("/") + "/flash/add", data=data, timeout=timeout)
    response.raise_for_status()
    body = response.text.strip()
    if body.startswith("failed"): raise RuntimeError(f"pyLoad rejected the links: {body}")
    return body

def filter_releases(releases: list[Release], args) -> list[Release]:
    """Customization point: add user-specific filters here."""
    selected = releases
    if args.resolution:
        wanted = args.resolution.casefold()
        selected = [r for r in selected if str(r.guessit.get("screen_size", "")).casefold() == wanted or wanted in r.title.casefold()]
    return selected

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", default="archive", help="Directory containing archived thread HTML")
    p.add_argument("--history", default="pyload_added.jsonl", help="JSONL history of successful submissions")
    p.add_argument("--pyload-url", default="http://localhost:9666")
    p.add_argument("--resolution", help="Optional filter, e.g. 720p")
    p.add_argument("--dry-run", action="store_true", help="List candidates without submitting")
    p.add_argument("--passwords", help="Optional archive password string passed to pyLoad")
    p.add_argument("--timeout", type=float, default=15.0)
    p.add_argument("--json-out", help="Write parsed release inventory as JSON")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    archive = Path(args.archive).expanduser()
    if not archive.is_dir(): p.error(f"archive directory does not exist: {archive}")
    # Stage 1: parse the entire archive.
    releases = parse_archive(archive)
    LOG.info("Parsed %d releases.", len(releases))
    if args.json_out:
        out = Path(args.json_out).expanduser(); out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([asdict(r) | {"key": r.key, "package_name": r.package_name} for r in releases], ensure_ascii=False, indent=2), encoding="utf-8")
        LOG.info("Wrote inventory to %s", out)
    # Stage 2: apply customizable filters.
    selected = filter_releases(releases, args)
    LOG.info("%d releases remain after filtering.", len(selected))
    # Stage 3: omit prior successful submissions.
    history_path = Path(args.history).expanduser()
    history = load_history(history_path)
    pending = [r for r in selected if r.key not in history]
    LOG.info("%d releases not in submission history.", len(pending))
    for r in pending: LOG.info("Candidate: %s | GuessIt=%s | links=%s", r.title, r.guessit, ", ".join(r.filecrypt_links))
    if args.dry_run:
        LOG.info("Dry run: nothing submitted."); return 0
    # Stage 4: one pyLoad package per release, log after handler accepts it.
    for r in pending:
        try:
            response = submit_links_to_pyload(r.filecrypt_links, r.package_name, base_url=args.pyload_url,
                                               passwords=args.passwords, timeout=args.timeout)
        except Exception:
            LOG.exception("Failed to submit %r; it will be retried next run.", r.title); continue
        append_history(history_path, r, response)
        LOG.info("Added to pyLoad: %s", r.title)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

filecrypt_scraper.py

``` python
#!/usr/bin/env python3
"""
Filecrypt container link extractor.

Uses a normal Playwright-controlled Firefox session. It does not attempt to
bypass Cloudflare or solve CAPTCHAs. In --headful mode, complete any browser
challenge yourself and press Enter in the terminal.

Input JSON:
[
  {"name": "Some Package", "filecrypt_url": "https://filecrypt.cc/Container/xxx.html"}
]

Output preserves each input object and adds:
  "decrypted_urls": [...]
  "decryption_error": "..."   (only when an error occurred)

Notes:
- DLC links are returned as .dlc container URLs, not expanded into hoster URLs.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import logging
import re
import sys
import time
import math
import random
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, unquote

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import playwright._impl._errors

from camoufox.sync_api import Camoufox

# TODO verify types
from playwright.sync_api import (
    Error as BrowserError,
    TimeoutError as BrowserTimeoutError,
    Page,
)

LOG = logging.getLogger("filecrypt_scraper")

CONTAINER_RE = re.compile(
    r"^https?://(?:www\.)?filecrypt\.(?:cc|co)/Container/\w+",
    re.IGNORECASE,
)
CNL_RE = re.compile(
    r"""CNLPOP\('([^']+)',\s*'([0-9a-fA-F]{32})',\s*'([^']+)',\s*'(.*?)'\);""",
    re.DOTALL,
)
WEBLINK_RE = re.compile(r"""<button\b[^>]*?onclick=["'][^"']*?/\*\d+\*/\('([\w/-]+)'""", re.I)
DLC_RE = re.compile(r"""onclick=["']DownloadDLC\(['"]([^'"]+)['"]\);["']""", re.I)
GO_RE = re.compile(r"https?://filecrypt\.cc/package_num\.php\?Action=Go&id=[\w-]+", re.I)

# Detect common challenge/interstitial markers. This is detection only.
CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "verify you are human",
    "cf-chl-",
    "challenge-platform",
    "security check",
)

def decrypt_cnl_payload(encoded: str, key_hex: str) -> list[str]:
    """Decrypt Filecrypt's CNL payload (AES-CBC; 16-byte key/IV)."""
    key = bytes.fromhex(key_hex)
    if len(key) != 16:
        raise ValueError(f"Expected 16-byte CNL key, got {len(key)} bytes")

    raw = base64.b64decode(unquote(encoded).replace(" ", "+"), validate=False)
    if not raw or len(raw) % 16:
        raise ValueError("CNL ciphertext is empty or not AES-block aligned")

    def decrypt(ciphertext: bytes, iv: bytes) -> bytes:
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        plain = decryptor.update(ciphertext) + decryptor.finalize()
        try:
            unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
            plain = unpadder.update(plain) + unpadder.finalize()
        except ValueError:
            plain = plain.rstrip(b"\x00")
        return plain.replace(b"\x00", b"")

    # pyLoad's CNL implementation uses the key as IV first. Some CNL payloads
    # instead carry the IV as the first AES block; try that documented fallback
    # if the first plaintext is not valid UTF-8.
    try:
        plaintext = decrypt(raw, key)
        text = plaintext.decode("utf-8").strip()
    except UnicodeDecodeError:
        if len(raw) <= 16:
            raise ValueError("CNL payload has no ciphertext after its IV")
        plaintext = decrypt(raw[16:], raw[:16])
        text = plaintext.decode("utf-8").strip()

    return [line.strip() for line in text.splitlines() if line.strip()]

def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result

def page_looks_challenged(page: Page) -> bool:
    try:
        sample = (page.title() + "\n" + page.locator("body").inner_text(timeout=2500)).lower()
    except BrowserError:
        try:
            sample = page.content().lower()
        except BrowserError:
            return False
    # return any(marker in sample for marker in CHALLENGE_MARKERS)
    for marker in CHALLENGE_MARKERS:
        if marker in sample:
            print(f"page_looks_challenged: found marker={marker!r}")
            return True
    return False

def wait_for_manual_challenge(page: Page, headful: bool, timeout_seconds: int) -> bool:
    if not page_looks_challenged(page):
        return True

    LOG.warning("A browser security/challenge page appears to be present: %s", page.url)

    # if not headful:
    #     LOG.error("Cannot complete an interactive challenge in headless mode.")
    #     return False

    cutcaptcha_shadow_host_selector = "div.cutcaptcha > div"
    cutcaptcha_spinner_selector = "span.cc__spinner"

    print("waiting for the captcha")
    time.sleep(5)

    print("solving cutcaptcha ...")

    shadow_host = page.locator(cutcaptcha_shadow_host_selector)
    print("shadow_host", shadow_host)
    # print("shadow_host dir", dir(shadow_host))
    print("shadow_host count:", shadow_host.count())
    print("shadow_host visible:", shadow_host.is_visible())
    print("shadow_host bounding box:", shadow_host.bounding_box())

    # hover the spinner to make it spin
    # move the browser-controlled pointer onto the element, generating the corresponding mouse events.
    # this is better than a synthetic javascript event:
    # "spinner.dispatchEvent(new MouseEvent("mouseenter", {bubbles: false, cancelable: false, view: window}));"
    # spinner = page.locator(cutcaptcha_spinner_selector)
    spinner = shadow_host.locator(cutcaptcha_spinner_selector)
    print("spinner", spinner)
    spinner_count_py = spinner.count()
    print("spinner count in Python:", spinner_count_py)
    js = (
        "() => {\n"
        f"  const host = document.querySelector({cutcaptcha_shadow_host_selector!r});\n"
        f"  return host?.shadowRootUnl?.querySelectorAll({cutcaptcha_spinner_selector!r}).length ?? 0;\n"
        "}\n"
    )
    spinner_count_js = page.evaluate(js)
    print("spinner count in JavaScript:", spinner_count_js)
    print("spinner visible:", spinner.is_visible())

    if spinner_count_py > 0:
        # if spinner_count_py == 0:
        # playwright._impl._errors.TimeoutError: Locator.hover: Timeout 30000ms exceeded.
        print("found spinner element in Python")
        print("spinner bounding box:", spinner.bounding_box())
        print("spinner.hover")
        spinner.hover()
    elif spinner_count_js > 0:
        # workaround: get the spinner bbox from javascript
        # and generate mouse events in python
        print("found spinner element in JavaScript")
        js = (
            "() => {\n"
            f"  var shadowHost = document.querySelector({cutcaptcha_shadow_host_selector!r});\n"
            # TODO check if shadowHost is null or undefined
            f"  var shadowRoot = shadowHost.shadowRootUnl;\n"
            # TODO check if shadowRoot is null or undefined
            f"  var spinner = shadowRoot.querySelector({cutcaptcha_spinner_selector!r});\n"
            # TODO check if spinner is null or undefined
            "  var rect = spinner.getBoundingClientRect();\n"
            "  return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };\n"
            "}\n"
        )
        spinner_rect = page.evaluate(js)
        print("spinner_rect", spinner_rect)

        x1 = math.ceil(spinner_rect["x"])
        x2 = math.floor(spinner_rect["x"] + spinner_rect["width"])
        y1 = math.ceil(spinner_rect["y"])
        y2 = math.floor(spinner_rect["y"] + spinner_rect["height"])
        print(f"spinner: x1={x1} x2={x2} y1={y1} y2={y2}")

        x = random.randint(x1, x2)
        y = random.randint(y1, y2)
        print("moving mouse over spinner:", (x, y))
        page.mouse.move(x, y)

        # wait some random time, then click the spinner
        dt = random.randint(100, 500) / 1000
        print(f"sleep {dt}")
        time.sleep(dt)

        print("clicking spinner:", (x, y))
        page.mouse.click(x, y)

    else:
        if 1:
            print(f"FIXME not found spinner element")
            time.sleep(60)
        raise RuntimeError(f"not found spinner element")

    # no! cutcaptcha detects "spinner.click()" as a synthetic event
    # and increases the difficulty
    r'''
    # wait some random time, then click the spinner
    dt = random.randint(100, 500) / 1000
    print(f"sleep {dt}")
    time.sleep(dt)

    js = (
        "() => {\n"
        # 'document.querySelector("#shadow-host").shadowRootUnl.querySelector("input").click()'
        f"  var shadowHost = document.querySelector({cutcaptcha_shadow_host_selector!r});\n"
        # TODO check if shadowHost is null or undefined
        f"  var shadowRoot = shadowHost.shadowRootUnl;\n"
        # TODO check if shadowRoot is null or undefined
        f"  var spinner = shadowRoot.querySelector({cutcaptcha_spinner_selector!r});\n"
        # TODO check if spinner is null or undefined
        # no! this works only in python
        # # move the browser-controlled pointer onto the element, generating the corresponding mouse events.
        # # this is better than a synthetic event:
        # # "spinner.dispatchEvent(new MouseEvent("mouseenter", {bubbles: false, cancelable: false, view: window}));"
        # "spinner.hover();\n"
        # wait some random time, then click the spinner
        f"  setTimeout(() => spinner.click(), {random.randint(100, 500)});\n"
        "}\n"
    )
    print("evaluating javascript:\n" + "    " + js.replace("\n", "\n    "))
    try:
        page.evaluate(js)
    # no: TypeError: catching classes that do not inherit from BaseException is not allowed
    # except BrowserError as exc:
    except playwright._impl._errors.Error as exc:
        # Page.evaluate: can't access property "shadowRootUnl", shadowHost is null
        print(f"evaluating javascript failed: {type(exc).__name__}: {exc}")
    '''

    # TODO wait for the proof of work challenge

    # TODO check if we have solved the captcha

    # time.sleep(2)
    # return

    # wait until shadow_host disappears
    # shadow_host = page.locator(cutcaptcha_shadow_host_selector)
    # print("shadow_host", shadow_host)
    print("waiting for shadow_host to disappear", end="", flush=True)
    # FIXME timeout, dont hang forever
    while True:
        count = shadow_host.count()
        if count == 0:
            print(" done")
            # TODO dynamic: return as soon as the page content has been loaded
            dt = 2
            print(f"waiting for the page content: dt={dt}")
            time.sleep(dt)
            return True
        # print(f" {count}", end="", flush=True)
        print(f".", end="", flush=True)
        time.sleep(1)

    print(
        "\n"
        "A site challenge is visible in Firefox.\n"
        "Complete it yourself in the browser window. Do not use automated "
        "challenge-solving.\n"
        "When the actual Filecrypt container page has loaded, return here "
        "and press Enter.\n",
        file=sys.stderr,
    )
    input("Press Enter to continue (Ctrl+C to stop): ")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not page.is_closed() and not page_looks_challenged(page):
            return True
        time.sleep(1)

    LOG.error("Challenge page is still present after the manual wait.")
    return False

def goto(page: Page, url: str, headful: bool, challenge_timeout: int) -> bool:
    print(f"goto: url={url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_load_state("networkidle", timeout=8_000)
    except BrowserTimeoutError:
        # Ad networks and analytics often keep connections open; DOM content
        # may still be fully usable.
        LOG.debug("Navigation/network-idle timeout for %s; inspecting current DOM", url)
    except BrowserError as exc:
        LOG.warning("Navigation failed for %s: %s", url, exc)
        return False

    print(f"goto: calling wait_for_manual_challenge")

    return wait_for_manual_challenge(page, headful, challenge_timeout)

def extract_package(
        context: BrowserContext,
        package: dict[str, Any],
        headful: bool,
        challenge_timeout: int,
    ) -> tuple[list[str], list[str]]:
    url = str(package.get("filecrypt_url", "")).strip()
    if not CONTAINER_RE.match(url):
        raise ValueError(f"Not a recognized Filecrypt container URL: {url!r}")

    page = context.new_page()
    urls: list[str] = []
    dlc_urls: list[str] = []

    try:
        if not goto(page, url, headful, challenge_timeout):
            raise RuntimeError("Filecrypt page did not become accessible")

        html = page.content()

        # Password-protected containers: ask interactively, then submit through
        # the page's own form. No password is written to the output JSON.
        password_input = page.locator('input[name="password"]#p4assw0rt')
        if password_input.count():
            password = package.get("password")
            if password is None and headful:
                password = input(f"Password for {package.get('name', url)!r}: ")
            if not password:
                raise RuntimeError(
                    "Container is password-protected; add a 'password' field "
                    "to this package or run with --headful."
                )
            password_input.fill(str(password))
            password_input.press("Enter")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=20_000)
            except BrowserTimeoutError:
                pass

            print(f"extract_package: calling wait_for_manual_challenge")

            if not wait_for_manual_challenge(page, headful, challenge_timeout):
                raise RuntimeError("Challenge after password submission was not completed")
            html = page.content()

        # CNL payloads: encrypted URLs embedded directly in the page.
        for _jk, key_hex, encrypted, package_name in CNL_RE.findall(html):
            try:
                urls.extend(decrypt_cnl_payload(encrypted, key_hex))
            except (ValueError, binascii.Error) as exc:
                LOG.warning("Could not decrypt a CNL payload: %s", exc)

        # Weblinks: use a separate tab for each short link and follow its Go URL.
        # Manual challenge is supported when headful.
        for link_id in unique(re.findall(WEBLINK_RE, html)):
            link_page = context.new_page()
            try:
                link_url = urljoin(url, f"/Link/{link_id}.html")
                if not goto(link_page, link_url, headful, challenge_timeout):
                    continue
                for attempt in range(5):
                    link_html = link_page.content()
                    go_match = GO_RE.search(link_html)
                    if go_match:
                        go_url = go_match.group(0)
                        try:
                            response = link_page.goto(
                                go_url, wait_until="domcontentloaded", timeout=30_000
                            )
                            final_url = response.url if response else link_page.url
                            if final_url and final_url != go_url:
                                urls.append(final_url.replace("\x10", ""))
                            elif link_page.url and link_page.url != go_url:
                                urls.append(link_page.url.replace("\x10", ""))
                        except BrowserError as exc:
                            LOG.debug("Following Go URL failed: %s", exc)
                        break
                    time.sleep(1 + attempt)
            finally:
                link_page.close()

        # DLC: this is a downloadable container, not a list of hoster URLs.
        for dlc_id in unique(DLC_RE.findall(html)):
            dlc_urls.append(urljoin(url, f"/DLC/{dlc_id}.dlc"))

        return unique(urls), unique(dlc_urls)
    finally:
        page.close()

def main() -> int:
    parser = argparse.ArgumentParser(description="Extract links from Filecrypt containers")
    parser.add_argument("input_json", type=Path, help="JSON file containing package objects")
    parser.add_argument("output_json", type=Path, help="Where to write enriched package JSON")
    parser.add_argument("--headful", action="store_true", help="Show Firefox and allow manual challenge completion")
    parser.add_argument("--profile-dir", type=Path, default=Path("./filecrypt-firefox-profile"),
                        help="Persistent Firefox profile directory")
    parser.add_argument("--firefox-executable", type=Path,
                        help="Optional path to a Playwright-compatible Firefox executable")
    parser.add_argument("--challenge-timeout", type=int, default=180,
                        help="Seconds to wait after you press Enter (default: 180)")
    parser.add_argument("--log-level", default="INFO",
                        choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        packages = json.loads(args.input_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"Cannot read input JSON: {exc}")
    if not isinstance(packages, list):
        parser.error("Input JSON must contain a top-level list")

    args.profile_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    camoufox_kwargs = dict(
        # headless=True,
        # headless=False, # debug: run the browser in headful mode
        headless=(not args.headful),

        # fix:
        # LeakWarning: Canvas and WebGL readback return random data,
        # as privacy.resistFingerprinting does in LibreWolf, Tor Browser and Mullvad Browser.
        # Stock Firefox does not do this, so the browser reads as a privacy-hardened Firefox.
        # It is on because the identity claims another OS or GPU than this machine's,
        # whose canvas would show the real one.
        # Pass `canvas_noise=False` to keep stock canvas behaviour.
        canvas_noise=False,

        # Human cursor movement
        humanize=True,

        config={
            # Read closed shadow roots
            "forceScopeAccess": True,
        },
    )

    with Camoufox(**camoufox_kwargs) as context:
        # page = context.new_page()
        # page.goto("https://example.com")
        # time.sleep(10) # debug: keep the browser open

        print(f"using Camoufox version {context.version}")

        # uBlock Origin needs about 10 seconds to init filter lists on its first run
        # so we waste some time here
        dt = 10
        print(f"waiting for uBlock Origin to init filter lists: dt={dt}")
        with context.new_page() as page:
            page.goto("https://ipfighter.com/bot-detection")
            # page.goto("https://antcpt.com/score_detector/")
            time.sleep(dt)

        try:
            for package_num, original in enumerate(packages, start=1):
                if not isinstance(original, dict):
                    LOG.warning("Item %d is not an object; preserving it unchanged", package_num)
                    results.append(original)
                    continue

                item = dict(original)
                label = item.get("name") or item.get("filecrypt_url") or f"package {package_num}"
                LOG.info(f"[{package_num}/{len(packages)}] Processing package {label}")

                try:
                    decrypted, dlc_urls = extract_package(
                        context, item, args.headful, args.challenge_timeout
                    )
                    item["decrypted_urls"] = decrypted
                    if dlc_urls:
                        item["dlc_urls"] = dlc_urls
                    item.pop("decryption_error", None)
                    LOG.info(f"Found {len(decrypted)} direct URLs, {len(dlc_urls)} DLC containers")
                    total_num_urls = len(decrypted) + len(dlc_urls)
                    if total_num_urls == 0:
                        print(f"error: found no URLs")
                        return 1
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    item["decrypted_urls"] = []
                    item["decryption_error"] = f"{type(exc).__name__}: {exc}"
                    LOG.exception("Failed to process %s", label)

                results.append(item)

                # Save incrementally so a later interruption does not lose work.
                args.output_json.parent.mkdir(parents=True, exist_ok=True)
                args.output_json.write_text(
                    json.dumps(results + packages[package_num:], ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

        finally:
            context.close()

    # Final output contains all packages, including any skipped/untouched tail.
    args.output_json.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    LOG.info(f"Done {args.output_json}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

## Response:

11/10/2026, 9:31:55 PM

I would integrate the two scripts by keeping their responsibilities separate and introducing a small orchestration layer in `myboerse_release_importer.py`.

The main design should be:

- **`myboerse_release_importer.py`** handles release discovery, filtering, package names, pyLoad submission, and submission history.
- **`filecrypt_scraper.py`** handles Filecrypt decryption using a shared Camoufox browser context and a single reusable page.
- **SQLite** stores successfully decrypted Filecrypt containers independently of releases, so the same container never needs to be decrypted again just because it appears in another release.

## 1. Proposed processing pipeline

<box border radius="xl" padding={3} gap={2}>
  <box background="surface-secondary" radius="lg" padding={3} align="center" gap={1}>
    **Archived MyBoerse HTML files**
    <text color="secondary" size="xs">Parse titles, Filecrypt URLs, GuessIt metadata</text>
  </box>
  <row justify="center"><icon name="arrow-down" color="tertiary"/></row>
  <box border radius="lg" padding={3} align="center" gap={1}>
    **Release filtering + submission history**
    <text color="secondary" size="xs">Skip excluded and previously submitted releases</text>
  </box>
  <row justify="center"><icon name="arrow-down" color="tertiary"/></row>
  <box border radius="lg" padding={3} align="center" gap={1}>
    **SQLite cache lookup for each Filecrypt URL**
    <text color="secondary" size="xs">Reuse decrypted results immediately on a cache hit</text>
  </box>
  <row justify="center"><icon name="arrow-down" color="tertiary"/></row>
  <box border radius="lg" padding={3} align="center" gap={1}>
    **Camoufox decryption on cache miss**
    <text color="secondary" size="xs">One browser context, one reusable page, lazy startup</text>
  </box>
  <row justify="center"><icon name="arrow-down" color="tertiary"/></row>
  <box background="rgba(22,163,74,0.07)" border={{size:1,color:"rgba(22,163,74,0.35)"}} radius="lg" padding={3} align="center" gap={1}>
    **Immediately commit decrypted URLs to SQLite**
    <text color="secondary" size="xs">Each successful container is persisted independently</text>
  </box>
  <row justify="center"><icon name="arrow-down" color="tertiary"/></row>
  <box background="surface-secondary" radius="lg" padding={3} align="center" gap={1}>
    **Submit one pyLoad package per release**
    <text color="secondary" size="xs">Combine decrypted links, deduplicate, submit, record success</text>
  </box>
</box>

One important distinction: **streaming should happen at two levels**. Each successful container decryption is immediately committed to SQLite, while each release is submitted to pyLoad as soon as all of its containers have been resolved.

This preserves your existing one-package-per-release behavior without waiting for the entire archive to finish.

## 2. Important edge cases

I would account for these explicitly:

1.  **Repeated containers:** Multiple releases can reference the same Filecrypt URL. The cache is keyed by a canonicalized container URL, not the release title.
2.  **Partial failures:** If a release contains three containers and the third fails, the first two remain cached. The release itself is not submitted with missing links.
3.  **Empty decryption results:** Never cache an empty result as successful, and never submit an empty package.
4.  **DLC URLs:** Your scraper currently returns these separately. They should not be mistaken for decrypted hoster URLs. By default, I would require actual decrypted URLs and treat DLC-only results as unresolved.
5.  **Duplicate submissions:** Retain your existing JSONL submission history, recording success only after pyLoad accepts the request.
6.  **Crash recovery:** Cache writes are committed immediately. A crash after pyLoad accepts a submission but before history is written still creates a small duplicate-submission risk, because the two systems cannot share an atomic transaction.

The browser should also start **only on the first cache miss**, so a fully cached run doesn't start Firefox at all.

## 3. Changes to `filecrypt_scraper.py`

The main refactor is to make `extract_package()` accept a `Page` instead of a `BrowserContext`.

Currently it creates a page for every container and additional pages for each Weblink. We can reuse the same page for both operations.

### A. Change the function signature

Add `BrowserContext` to your imports if you still need it elsewhere, but the extraction function itself should use:

Remove the following from inside `extract_package()`:

Also remove the surrounding `try: ... finally: page.close()` because the caller now owns the page's lifetime.

### B. Replace the Weblink extraction section

Your existing implementation opens a separate tab for every Weblink. Instead, collect the Weblink IDs from the original container HTML and navigate the same page to each link.

Replace the entire `# Weblinks:` section with:

There is one subtlety here: navigating directly to a hoster's URL can trigger downloads, external protocol handlers, or redirects that do not complete normally. Your original code already has that limitation, so this refactor preserves its general behavior rather than changing the extraction strategy.

Also, make sure the existing `html = page.content()` captured before Weblink navigation continues to be used for the DLC extraction.

### C. Update the standalone scraper

In `filecrypt_scraper.py`'s `main()`, create one page:

This requires adjusting the surrounding loop and error handling, but not changing your decryption algorithms.

**One additional fix:** your `wait_for_manual_challenge()` currently contains an unbounded `while True` loop. I would replace that with a deadline based on `time.monotonic()`, so a failed challenge cannot block the entire import indefinitely.

The existing function also mixes automatic challenge interaction with a manual fallback. I would keep that logic separate from the importer and ensure the timeout is respected regardless of which challenge-handling approach you use.

## 4. Add a SQLite-backed decryption service

I recommend creating a third file, `filecrypt_cache.py`, rather than mixing database and browser lifecycle management into either existing script.

This module provides a simple interface:

It automatically checks SQLite first, starts Camoufox only when necessary, and commits successful results before returning.

Create `filecrypt_cache.py`:

<CodeBlock language="python" editable>
from __future__ import annotations

import json  
import logging  
import sqlite3  
from contextlib import ExitStack  
from datetime import datetime, timezone  
from pathlib import Path  
from urllib.parse import urlsplit, urlunsplit

from camoufox.sync_api import Camoufox

from filecrypt_scraper import extract_package, unique

LOG = logging.getLogger(**name**)

def canonical_url(url: str) -\> str:  
"""Normalize the scheme and hostname without changing container IDs."""  
p = urlsplit(url.strip())  
if p.scheme.lower() not in ("http", "https"):  
raise ValueError(f"Invalid Filecrypt URL: {url!r}")  
if p.hostname not in ("filecrypt.cc", "[www.filecrypt.cc](http://www.filecrypt.cc)"):  
raise ValueError(f"Invalid Filecrypt host: {url!r}")  
return urlunsplit((  
"https",  
"filecrypt.cc",  
p.path,  
p.query,  
"",  
))

class FilecryptResolver:  
def **init**(  
self,  
database: str \| Path,  
\*,  
headful: bool = False,  
challenge_timeout: int = 180,  
):  
self.database = Path(database)  
self.headful = headful  
self.challenge_timeout = challenge_timeout

        self.db = None
        self.stack = None
        self.page = None

    def __enter__(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)

        self.db = sqlite3.connect(self.database, timeout=30)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS decrypted_containers (
                container_url TEXT PRIMARY KEY,
                decrypted_urls TEXT NOT NULL,
                dlc_urls TEXT NOT NULL,
                decrypted_at TEXT NOT NULL
            )
        """)
        self.db.commit()

        self.stack = ExitStack()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self.stack is not None:
                self.stack.close()
        finally:
            if self.db is not None:
                self.db.close()

    def _get_page(self):
        """Start Firefox lazily and create exactly one reusable page."""
        if self.page is None:
            LOG.info("Starting Camoufox (first cache miss)")

            context = self.stack.enter_context(Camoufox(
                headless=not self.headful,
                canvas_noise=False,
                humanize=True,
                config={"forceScopeAccess": True},
            ))

            self.page = context.new_page()
            self.stack.callback(self.page.close)

            LOG.info("Camoufox version: %s", context.version)

        return self.page

    def resolve(
        self,
        container_url: str,
        *,
        package_name: str = "",
        password: str | None = None,
    ) -> list[str]:
        key = canonical_url(container_url)

        row = self.db.execute(
            """
            SELECT decrypted_urls
            FROM decrypted_containers
            WHERE container_url = ?
            """,
            (key,),
        ).fetchone()

        if row is not None:
            LOG.info("Cache HIT: %s", key)
            return json.loads(row[0])

        LOG.info("Cache MISS: %s", key)

        package = {
            "name": package_name,
            "filecrypt_url": key,
        }
        if password is not None:
            package["password"] = password

        urls, dlc_urls = extract_package(
            self._get_page(),
            package,
            self.headful,
            self.challenge_timeout,
        )

        urls = unique(urls)
        dlc_urls = unique(dlc_urls)

        # Cache only successful hoster URL extraction.
        # DLC-only results are deliberately not considered complete.
        if not urls:
            raise RuntimeError(
                f"No decrypted hoster URLs found for {key} "
                f"({len(dlc_urls)} DLC containers)"
            )

        # Commit immediately, before returning to the importer.
        with self.db:
            self.db.execute(
                """
                INSERT INTO decrypted_containers
                    (container_url, decrypted_urls, dlc_urls, decrypted_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(container_url) DO UPDATE SET
                    decrypted_urls = excluded.decrypted_urls,
                    dlc_urls = excluded.dlc_urls,
                    decrypted_at = excluded.decrypted_at
                """,
                (
                    key,
                    json.dumps(urls, ensure_ascii=False),
                    json.dumps(dlc_urls, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        LOG.info("Cached %d URLs for %s", len(urls), key)
        return urls

</CodeBlock>

The database will contain records conceptually like:

| container_url | decrypted_urls | decrypted_at |
|----|----|----|
| `https://filecrypt.cc/Container/abc.html` | `["https://hoster.example/file1", "https://hoster.example/file2"]` | UTC timestamp |

SQLite provides transactionally committed writes, so successful decryption results survive an ordinary process interruption after the commit.

One assumption in this implementation is that the same Filecrypt container URL always produces the same useful link set. If password-protected containers can produce different results depending on the supplied password, the cache key will need to account for that without storing passwords in plaintext.

## 5. Integrate the resolver into `myboerse_release_importer.py`

We can keep most of your existing parser, GuessIt integration, filtering, pyLoad submission, and JSONL history unchanged.

### A. Add imports

### B. Make archive parsing a generator

Your existing `parse_archive()` collects every release before starting any downloads. For genuine streaming, introduce:

You can retain `parse_archive()` for compatibility:

This means we can parse, filter, decrypt, and submit one release before parsing the next HTML file.

### C. Add a streaming submission function

This deliberately submits a release only when every Filecrypt container resolves successfully.

### D. Replace the `main()` processing stages

Keep your existing argument parser, but add:

Then replace the current Stage 1-4 processing code, after archive validation, with:

<CodeBlock language="python" editable>
    history_path = Path(args.history).expanduser()
    history = load_history(history_path)

    parsed_count = 0
    selected_count = 0
    submitted_count = 0
    failed_count = 0
    skipped_count = 0

    inventory = [] if args.json_out else None

    with FilecryptResolver(
        Path(args.cache_db).expanduser(),
        headful=args.headful,
        challenge_timeout=args.challenge_timeout,
    ) as resolver:

        for release in iter_archive(archive):
            parsed_count += 1

            if inventory is not None:
                inventory.append(
                    asdict(release) | {
                        "key": release.key,
                        "package_name": release.package_name,
                    }
                )

            # Apply existing customizable filters.
            if not filter_releases([release], args):
                continue

            selected_count += 1

            # Skip releases already accepted by pyLoad.
            if release.key in history:
                skipped_count += 1
                continue

            LOG.info(
                "Processing release: %s (%d containers)",
                release.title,
                len(release.filecrypt_links),
            )

            if args.dry_run:
                LOG.info(
                    "DRY RUN: %s | GuessIt=%s | links=%s",
                    release.title,
                    release.guessit,
                    release.filecrypt_links,
                )
                continue

            try:
                response = process_release(
                    release,
                    resolver,
                    args,
                )

                # Record success immediately.
                append_history(
                    history_path,
                    release,
                    response,
                )

                # Also update in-memory history so duplicates
                # within this run are skipped.
                history[release.key] = {
                    "key": release.key,
                    "pyload_response": response,
                }

                submitted_count += 1
                LOG.info(
                    "Successfully added to pyLoad: %s",
                    release.title,
                )

            except KeyboardInterrupt:
                raise

            except Exception:
                failed_count += 1
                LOG.exception(
                    "Failed processing %r; will retry next run",
                    release.title,
                )

    if inventory is not None:
        out = Path(args.json_out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                inventory,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        LOG.info("Wrote inventory to %s", out)

    LOG.info(
        "Finished: parsed=%d selected=%d "
        "submitted=%d skipped=%d failed=%d",
        parsed_count,
        selected_count,
        submitted_count,
        skipped_count,
        failed_count,
    )

    return 1 if failed_count else 0

</CodeBlock>

Notice that `history` is updated immediately after a successful submission. Your original implementation did not update the in-memory dictionary after writing the JSONL record, so duplicate releases encountered later in the same run could be submitted twice.

This version fixes that.

## 6. Example usage

<box gap={2}>
  <text weight="medium" size="sm">First, inspect the releases without starting Firefox:</text>
  ```bash
  python myboerse_release_importer.py \
      --archive archive/myboerse \
      --dry-run
  ```

<text weight="medium" size="sm">Run the integrated importer:</text>

``` bash
python myboerse_release_importer.py \
    --archive archive/myboerse \
    --cache-db filecrypt_cache.sqlite3 \
    --history pyload_added.jsonl \
    --pyload-url http://localhost:9666
```

<text weight="medium" size="sm">For interactive browser challenges:</text>

``` bash
python myboerse_release_importer.py \
    --archive archive/myboerse \
    --headful \
    --verbose
```

</box>

An example execution would look like:

## 7. Two improvements I would make before using this on a large archive

**First, verify that each container was fully decrypted.** Your current `extract_package()` silently continues when an individual Weblink fails. That means it can return a nonempty but incomplete set of URLs, which the cache would incorrectly consider successful forever.

I would change the scraper so it tracks the number of expected Weblinks and raises an exception if any cannot be resolved. It should also treat failed CNL decryption as an incomplete result. This ensures that only complete results are cached. Containers intentionally containing both DLC and hoster URLs need an explicit completeness policy.

**Second, strengthen the pyLoad submission history.** Your current JSONL approach is adequate for normal sequential execution, but it cannot guarantee exactly-once submission if pyLoad accepts a package and the importer crashes before recording success.

For now, I would keep the JSONL history for compatibility. Later, you could move submission tracking into SQLite, introduce an intermediate `submitting` state, and reconcile uncertain submissions against pyLoad before retrying. That would provide better recovery, although true exactly-once behavior still depends on pyLoad's API capabilities.

One more detail: the proposed `canonical_url()` deliberately preserves URL paths and query strings. It should not normalize container IDs aggressively until you've confirmed which URL variations Filecrypt considers equivalent.

## 8. Recommended final structure

This gives you the core behavior you requested: one browser context, one page, lazy browser initialization, immediate SQLite commits, release-by-release streaming, and one pyLoad submission per successfully resolved release.

**I would implement the strict decryption-completeness check before treating this as production-ready**, because caching partially decrypted containers is the most consequential remaining correctness issue.

## Prompt:

11/10/2026, 10:03:38 PM

> your `wait_for_manual_challenge()` currently contains an unbounded `while True` loop. I would replace that with a deadline based on `time.monotonic()`, so a failed challenge cannot block the entire import indefinitely.

yes, please suggest a fix

now i have refactored the main function in filecrypt_scraper.py so the inner function decrypt_packages also works without input and output files, so we can re-use the inner function decrypt_packages

    def main() -> int:
        parser = argparse.ArgumentParser(description="Extract links from Filecrypt containers")
        parser.add_argument("input_json", type=Path, help="JSON file containing package objects")
        parser.add_argument("output_json", type=Path, help="Where to write enriched package JSON")
        parser.add_argument("--headful", action="store_true", help="Show Firefox and allow manual challenge completion")
        parser.add_argument("--challenge-timeout", type=int, default=180,
                            help="Seconds to wait after you press Enter (default: 180)")
        parser.add_argument("--log-level", default="INFO",
                            choices=("DEBUG", "INFO", "WARNING", "ERROR"))
        args = parser.parse_args()

        logging.basicConfig(
            level=getattr(logging, args.log_level),
            format="%(asctime)s %(levelname)s %(message)s",
        )

        try:
            packages = json.loads(args.input_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"Cannot read input JSON: {exc}")
        if not isinstance(packages, list):
            parser.error("Input JSON must contain a top-level list")

        results: list[dict[str, Any]] = []

        for package_num, decrypted_package in enumerate(decrypt_packages(packages, args), start=1):
            results.append(decrypted_package)

            # Save incrementally so a later interruption does not lose work.
            LOG.info(f"Writing {args.output_json}")
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(
                json.dumps(results + packages[package_num:], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        r'''
        # Final output contains all packages, including any skipped/untouched tail.
        args.output_json.write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        LOG.info(f"Done {args.output_json}")
        '''

    def decrypt_packages(packages, args):

        camoufox_kwargs = dict(
            # headless=True,
            # headless=False, # debug: run the browser in headful mode
            headless=(not args.headful),

            # fix:
            # LeakWarning: Canvas and WebGL readback return random data,
            # as privacy.resistFingerprinting does in LibreWolf, Tor Browser and Mullvad Browser.
            # Stock Firefox does not do this, so the browser reads as a privacy-hardened Firefox.
            # It is on because the identity claims another OS or GPU than this machine's,
            # whose canvas would show the real one.
            # Pass `canvas_noise=False` to keep stock canvas behaviour.
            canvas_noise=False,

            # Human cursor movement
            humanize=True,

            config={
                # Read closed shadow roots
                "forceScopeAccess": True,
            },
        )

        with (
                Camoufox(**camoufox_kwargs) as context,
                context.new_page() as page,
            ):
            # page = context.new_page()
            # page.goto("https://example.com")
            # time.sleep(10) # debug: keep the browser open

            print(f"using Camoufox version {context.version}")

            # uBlock Origin needs about 10 seconds to init filter lists on its first run
            # so we waste some time here
            dt = 10
            print(f"waiting for uBlock Origin to init filter lists: dt={dt}")
            if 1: # keep indent
                page.goto("https://ipfighter.com/bot-detection")
                # page.goto("https://antcpt.com/score_detector/")
                time.sleep(dt)

            # try:
            if 1: # keep indent
                for package_num, original in enumerate(packages, start=1):
                    if not isinstance(original, dict):
                        LOG.warning("Item %d is not an object; preserving it unchanged", package_num)
                        # results.append(original)
                        yield original
                        continue

                    item = dict(original)
                    label = item.get("name") or item.get("filecrypt_url") or f"package {package_num}"
                    LOG.info(f"[{package_num}/{len(packages)}] Processing package {label}")

                    try:
                        decrypted, dlc_urls = extract_package(
                            page, item, args.headful, args.challenge_timeout
                        )
                        item["decrypted_urls"] = decrypted
                        if dlc_urls:
                            item["dlc_urls"] = dlc_urls
                        item.pop("decryption_error", None)
                        LOG.info(f"Found {len(decrypted)} direct URLs, {len(dlc_urls)} DLC containers")
                        total_num_urls = len(decrypted) + len(dlc_urls)
                        if total_num_urls == 0:
                            print(f"error: found no URLs")
                            # return 1
                            yield original
                            continue
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        item["decrypted_urls"] = []
                        item["decryption_error"] = f"{type(exc).__name__}: {exc}"
                        LOG.exception("Failed to process %s", label)

                    yield item

            r'''
            finally:
                # TODO is this needed with the context block?
                page.close()
                context.close()
            '''

> I recommend creating a third file, `filecrypt_cache.py`, rather than mixing database and browser lifecycle management into either existing script.

nah, i want to have the myboerse_release_importer.py script as the main script, which uses the decrypt_packages function to decrypt a stream of filecrypt containers

## Response:

11/10/2026, 10:04:31 PM

Agreed. With your new generator-based `decrypt_packages()`, there's no need for a third module.

I'd keep the responsibilities as follows:

- `filecrypt_scraper.py` owns Camoufox, the reusable browser page, and Filecrypt decryption.
- `myboerse_release_importer.py` owns SQLite caching, release filtering, pyLoad submission, and history.
- The importer passes a lazy stream of uncached Filecrypt containers into `decrypt_packages()` and consumes its results as they're yielded.

There is one important architectural detail: **the SQLite cache should be checked before each container enters the decryption generator**, and each result should be committed immediately after the generator yields it.

That allows Firefox to remain open while the importer writes to SQLite and submits completed releases to pyLoad.

## 1. Fix the unbounded challenge wait

In `wait_for_manual_challenge()`, replace your current block:

with:

This preserves your existing challenge-handling logic while preventing an indefinite wait for the shadow host to disappear.

Two refinements are worth considering:

1.  **Start the deadline before challenge interaction**, not immediately before the final waiting loop. Otherwise, the earlier `time.sleep(5)`, locator operations, and interaction steps aren't included in the timeout.
2.  Your `shadow_host.bounding_box()` and `spinner.hover()` calls can themselves block for Playwright's default timeout. Set explicit shorter timeouts where appropriate.

For example, near the beginning of the function:

Then use `timeout=min(5000, remaining_ms())` for Playwright calls that accept a timeout. This gives the challenge one overall deadline rather than several independent timeouts.

Note that synchronous calls such as `input()` and certain blocking browser operations need separate handling if you want a strict wall-clock limit. The deadline check alone cannot interrupt a blocking call.

## 2. Make `decrypt_packages()` accept a true stream

Your refactoring is almost there. The main thing I'd change is that `decrypt_packages()` should accept an `Iterable`, not assume `packages` is a list.

Currently:

This prevents passing a generator without a known length.

I'd also remove the `yield original` behavior when decryption returns zero URLs. That hides the failure from the importer.

Here is how I'd rewrite `decrypt_packages()` while keeping your existing Camoufox settings.

<CodeBlock language="python" editable>
from collections.abc import Iterable, Iterator
from typing import Any

def decrypt_packages(  
packages: Iterable\[dict\[str, Any\]\],  
args,  
) -\> Iterator\[dict\[str, Any\]\]:  
"""  
Decrypt a stream of Filecrypt packages.

    Starts Camoufox once, uses one page, and yields each
    result as soon as it has been processed.

    Does not perform caching or pyLoad submission.
    """

    camoufox_kwargs = dict(
        headless=not args.headful,
        canvas_noise=False,
        humanize=True,
        config={"forceScopeAccess": True},
    )

    with Camoufox(**camoufox_kwargs) as context:
        LOG.info("Camoufox version: %s", context.version)

        with context.new_page() as page:
            LOG.info("Waiting for browser initialization")

            page.goto("https://ipfighter.com/bot-detection")
            time.sleep(10)

            for package_num, original in enumerate(packages, start=1):
                item = dict(original)

                label = (
                    item.get("name")
                    or item.get("filecrypt_url")
                    or f"package {package_num}"
                )

                LOG.info(
                    "[%d] Decrypting %s",
                    package_num,
                    label,
                )

                try:
                    decrypted, dlc_urls = extract_package(
                        page,
                        item,
                        args.headful,
                        args.challenge_timeout,
                    )

                    item["decrypted_urls"] = unique(decrypted)
                    item["dlc_urls"] = unique(dlc_urls)
                    item.pop("decryption_error", None)

                    if not item["decrypted_urls"]:
                        raise RuntimeError(
                            "No decrypted hoster URLs found "
                            f"({len(dlc_urls)} DLC URLs)"
                        )

                    LOG.info(
                        "Decrypted %d URLs from %s",
                        len(item["decrypted_urls"]),
                        label,
                    )

                except KeyboardInterrupt:
                    raise

                except Exception as exc:
                    item["decrypted_urls"] = []
                    item["decryption_error"] = (
                        f"{type(exc).__name__}: {exc}"
                    )

                    LOG.exception(
                        "Failed to decrypt %s",
                        label,
                    )

                yield item

</CodeBlock>

The important properties are:

- `packages` can be a list or generator.
- Camoufox is started only once per invocation.
- Exactly one page is created by `decrypt_packages()`.
- Each result is yielded immediately.
- The caller decides what to do with successful or failed results.

A generator pauses at `yield`, so the importer can write the result to SQLite before the browser begins decrypting the next container.

Your standalone `main()` can continue using this function unchanged apart from returning `0` at the end.

One caveat: this generator starts Firefox as soon as iteration begins. We'll avoid unnecessary browser startup in the importer by checking SQLite before invoking it.

## 3. SQLite cache inside `myboerse_release_importer.py`

I would keep the cache implementation small and use Python's built-in `sqlite3`.

Add these imports:

Then add:

<CodeBlock language="python" editable>
def init_cache(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS filecrypt_cache (
            url TEXT PRIMARY KEY,
            decrypted_urls TEXT NOT NULL,
            cached_at TEXT NOT NULL
        )
    """)
    db.commit()

def get_cached_urls(  
db: sqlite3.Connection,  
url: str,  
) -\> list\[str\] \| None:  
row = db.execute(  
"SELECT decrypted_urls FROM filecrypt_cache WHERE url = ?",  
(url,),  
).fetchone()

    if row is None:
        return None

    return json.loads(row[0])

def cache_decrypted_urls(  
db: sqlite3.Connection,  
url: str,  
urls: list\[str\],  
) -\> None:  
if not urls:  
raise ValueError("Refusing to cache empty URL list")

    with db:
        db.execute(
            """
            INSERT INTO filecrypt_cache
                (url, decrypted_urls, cached_at)
            VALUES (?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                decrypted_urls = excluded.decrypted_urls,
                cached_at = excluded.cached_at
            """,
            (
                url,
                json.dumps(urls, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

</CodeBlock>

This version uses the exact Filecrypt URL as its key. It is sufficient if your archive contains consistent URLs. A separate canonicalization function can be added later to merge equivalent `http`/`https` and `www` variants.

## 4. Connect the stream to the cache and pyLoad

There is an important design choice here.

You could generate every uncached container in the archive, decrypt them all, and then submit releases. However, that would delay pyLoad submissions unnecessarily.

Instead, I recommend a **release-oriented generator** that checks the cache and invokes `decrypt_packages()` only for uncached containers.

The browser can then remain open while the importer processes successive releases.

To accomplish this, we need to make sure the same `decrypt_packages()` generator receives all cache misses, rather than creating a new generator for each release.

The cleanest approach is to create a generator that supplies uncached containers on demand, while the importer consumes the decrypted results in the same order.

### A. Prepare releases and identify cache misses

For this version, I'd retain your existing archive parsing and filtering stages. They build the release inventory first, but **decryption, caching, and pyLoad submission remain streaming**.

That keeps the integration simpler and ensures we can know when all containers belonging to a release have been resolved.

Add the following helper to `myboerse_release_importer.py`:

<CodeBlock language="python" editable>
def submit_resolved_release(
    release: Release,
    urls: list[str],
    args,
    history_path: Path,
    history: dict,
) -> None:
    urls = unique(urls)

    if not urls:
        raise ValueError(
            f"No decrypted URLs for {release.title}"
        )

    response = submit_links_to_pyload(
        urls,
        release.package_name,
        base_url=args.pyload_url,
        passwords=args.passwords,
        timeout=args.timeout,
    )

    append_history(history_path, release, response)
    history[release.key] = {
        "key": release.key,
        "pyload_response": response,
    }

    LOG.info(
        "Added to pyLoad: %s (%d URLs)",
        release.package_name,
        len(urls),
    )

</CodeBlock>

### B. Implement the streaming pipeline

This function creates a queue of uncached container requests, then passes that queue into your existing `decrypt_packages()` generator.

A release is submitted as soon as its final missing container is decrypted and cached.

<CodeBlock language="python" editable>
def process_releases(
    releases: list[Release],
    args,
    history_path: Path,
    history: dict,
) -> int:
    failures = 0

    with sqlite3.connect(args.cache_db) as db:
        init_cache(db)

        # State for each pending release.
        states = {}
        requests = []

        for release in releases:
            if release.key in history:
                continue

            # Avoid processing duplicate release keys.
            if release.key in states:
                continue

            state = {
                "release": release,
                "urls": [],
                "remaining": 0,
                "failed": False,
            }
            states[release.key] = state

            for container_url in unique(release.filecrypt_links):
                cached = get_cached_urls(db, container_url)

                if cached is not None:
                    LOG.info("Cache HIT: %s", container_url)
                    state["urls"].extend(cached)
                    continue

                LOG.info("Cache MISS: %s", container_url)
                state["remaining"] += 1

                requests.append({
                    "name": release.package_name,
                    "filecrypt_url": container_url,
                    "release_key": release.key,
                })

        # Submit fully cached releases without starting Firefox.
        for state in states.values():
            if state["remaining"] != 0:
                continue

            try:
                submit_resolved_release(
                    state["release"],
                    state["urls"],
                    args,
                    history_path,
                    history,
                )
            except Exception:
                failures += 1
                LOG.exception(
                    "Failed submitting %s",
                    state["release"].title,
                )

        if not requests:
            LOG.info("No containers need decryption")
            return failures

        # The generator starts Camoufox once and reuses its page.
        for result in decrypt_packages(requests, args):
            release_key = result["release_key"]
            state = states[release_key]
            container_url = result["filecrypt_url"]

            error = result.get("decryption_error")
            urls = result.get("decrypted_urls", [])

            if error or not urls:
                state["failed"] = True
                LOG.error(
                    "Failed container %s: %s",
                    container_url,
                    error or "No URLs",
                )
            else:
                # Persist immediately, before processing
                # the next container.
                try:
                    cache_decrypted_urls(
                        db,
                        container_url,
                        urls,
                    )
                    state["urls"].extend(urls)
                except Exception:
                    state["failed"] = True
                    LOG.exception(
                        "Could not cache %s",
                        container_url,
                    )

            state["remaining"] -= 1

            if state["remaining"] != 0:
                continue

            if state["failed"]:
                failures += 1
                LOG.warning(
                    "Skipping incomplete release %s",
                    state["release"].title,
                )
                continue

            try:
                submit_resolved_release(
                    state["release"],
                    state["urls"],
                    args,
                    history_path,
                    history,
                )
            except Exception:
                failures += 1
                LOG.exception(
                    "Failed submitting %s",
                    state["release"].title,
                )

    return failures

</CodeBlock>

This is the simplest version using your existing generator interface, but there are two limitations worth noting.

**First:** `requests` is currently a list. That's not a problem for browser memory, since it contains only small dictionaries, but it does mean the archive and cache lookups are performed before decryption begins. We can change that later if fully lazy archive processing becomes important.

**Second:** when the same uncached container appears in multiple releases, it will appear multiple times in `requests`. We should eliminate that duplication before running the browser.

## 5. Deduplicate cache misses across releases

This is essential for your requirement that each Filecrypt container be decrypted only once, even during the first run when the cache is empty.

In `process_releases()`, add a dictionary before the release loop:

Then replace:

with:

Finally, replace the entire result-processing loop, beginning with `for result in decrypt_packages(requests, args):`, with:

<CodeBlock language="python" editable>
        for result in decrypt_packages(requests, args):
            container_url = result["filecrypt_url"]
            dependent_keys = container_dependents[container_url]

            error = result.get("decryption_error")
            urls = result.get("decrypted_urls", [])

            if not error and urls:
                try:
                    # Cache immediately, once per container.
                    cache_decrypted_urls(db, container_url, urls)
                except Exception as exc:
                    LOG.exception("Cache write failed: %s", container_url)
                    error = f"Cache write failed: {exc}"
            else:
                error = error or "No decrypted URLs"

            # Distribute the result to every release that
            # references this container.
            for release_key in dependent_keys:
                state = states[release_key]

                if error:
                    state["failed"] = True
                else:
                    state["urls"].extend(urls)

                state["remaining"] -= 1

                if state["remaining"] != 0:
                    continue

                if state["failed"]:
                    failures += 1
                    LOG.warning(
                        "Skipping incomplete release %s",
                        state["release"].title,
                    )
                    continue

                try:
                    submit_resolved_release(
                        state["release"],
                        state["urls"],
                        args,
                        history_path,
                        history,
                    )
                except Exception:
                    failures += 1
                    LOG.exception(
                        "Failed submitting %s",
                        state["release"].title,
                    )


    Now one decryption can satisfy any number of releases, and each completed release is submitted independently.

    For robustness, I would also catch exceptions raised while advancing `decrypt_packages()` itself. Its per-package exception handler doesn't cover browser startup failures or a generator-wide interruption. If that happens, affected releases should remain unsubmitted and be retried later.

    ## 6. Call the pipeline from `main()`

    Add:

    ```python
    p.add_argument(
        "--cache-db",
        default="filecrypt_cache.sqlite3",
    )
    p.add_argument("--headful", action="store_true")
    p.add_argument("--challenge-timeout", type=int, default=180)

Then, after parsing, filtering, and handling `--dry-run`:

``` python
failures = process_releases(
    selected,
    args,
    history_path,
    history,
)

return 1 if failures else 0
```

One final consideration: `decrypt_packages()` now treats a nonempty set of URLs as success, but your existing scraper may silently skip failed individual Weblinks. Before relying on the cache long-term, I would make those failures propagate so incomplete results are never cached as complete.

### Resulting architecture

``` text
myboerse_release_importer.py
    |
    +-- parse and filter releases
    |
    +-- check SQLite cache
    |       |
    |       +-- cached URLs
    |       |
    |       +-- unique uncached containers
    |               |
    |               +-- decrypt_packages(...)
    |                       |
    |                       +-- one Camoufox context
    |                       +-- one reusable page
    |                       +-- yield decrypted result
    |
    +-- immediately cache each successful result
    |
    +-- distribute URLs to dependent releases
    |
    +-- submit each complete release to pyLoad
    |
    +-- immediately record submission history
```

This integrates directly with your refactored generator and doesn't require `filecrypt_cache.py`.

**The next optimization I'd prioritize is making the release inventory itself lazy**, so parsing, filtering, cache lookup, decryption, and pyLoad submission all happen in a single streaming pipeline. The current approach already streams the expensive browser work and pyLoad submissions, while retaining the simpler upfront inventory stage.

## Prompt:

11/11/2026, 8:58:48 AM

# Selected text:

## Selection 1

Deduplicate cache misses across releases

## My request:

instead of your proposed double-bookkeeping (`requests` list and `container_dependents` dict), i would use only a dict like `container_dependents`, keyed by `filecrypt_url`, so if we later find other packages with the same `filecrypt_url` (this should never happen but is possible in theory = bad data) then we can append these other package names the list of package names in `container_dependents[filecrypt_url]["package_names"]`

## Response:

11/11/2026, 8:58:50 AM

Yes, that is cleaner. I'd use `container_dependents` as the **single source of truth** for uncached Filecrypt containers, with each dictionary entry containing the container URL's dependent releases.

For example:

I'd retain `release_keys` alongside `package_names`, because your existing release state and submission history use `Release.key` to identify releases. Package names aren't necessarily unique.

## 1. Build the dictionary directly

Replace the `requests` list and the previous `container_dependents` logic with:

Because dictionary keys are unique, every uncached Filecrypt container appears exactly once.

## 2. Feed the dictionary directly into `decrypt_packages()`

Your `decrypt_packages()` generator expects dictionaries containing `name` and `filecrypt_url`.

We can generate those lazily from `container_dependents`:

Then:

No intermediate `requests` list is necessary.

You could also use a generator expression:

## 3. Distribute decrypted URLs to dependent releases

The result-processing loop remains almost identical:

## 4. An even simpler dictionary structure

Since the importer already has `states`, you could eliminate `package_names` entirely and store only release keys:

Then derive the package name when constructing the input:

This avoids storing package names twice and guarantees that package names always come from the original `Release` objects.

**I'd prefer this last approach**, unless you specifically want `container_dependents` to contain the package names for logging, debugging, or exporting the mapping. It gives you one dictionary keyed by Filecrypt URL, with references to all dependent releases, without redundant metadata.

One important distinction: this deduplicates **decryption**, not pyLoad submissions. If two distinct releases reference the same container, both will still receive their own pyLoad package. That matches the existing release-oriented history model; if you instead want a container submitted to pyLoad only once globally, the submission policy should be changed separately.

## Prompt:

11/11/2026, 8:59:27 AM

also we should rename `container_dependents`...

## Response:

11/11/2026, 8:59:29 AM

I'd rename it to **`pending_containers`** because the dictionary represents Filecrypt containers that are not yet cached and still need decryption.

Then name the generator `iter_pending_packages()` to avoid a naming collision:

And consume it with:

I prefer `pending_containers` over `container_dependents` because it describes **what the dictionary contains and why it exists**, rather than emphasizing the dependency relationship.

If you want to make the purpose even more explicit, `containers_to_decrypt` is another good option.

## Prompt:

11/11/2026, 9:04:30 AM

# Selected text:

## Selection 1

Package names aren't necessarily unique

## My request:

yeah, we should make package names unique by appending the forum thread ID like

`Some Package (t1836094)`

the forum thread ID is stored both in the HTML filename

    archive/myboerse/1836094.html

and in the HTML content

    <!DOCTYPE html><html ... data-content-key="thread-1836094" ...>

## Response:

11/11/2026, 9:04:32 AM

Yes. I'd add `thread_id` as a field to the `Release` dataclass and derive the unique pyLoad package name from it.

I'd use the **HTML filename as the primary source**, with `data-content-key` as a fallback. If both are available, we can also verify that they match.

## 1. Extend the `Release` dataclass

This also simplifies the release key. Since a MyBoerse thread ID uniquely identifies a thread, there's no need to hash the title and Filecrypt URLs to identify the release.

However, changing `Release.key` would invalidate matching against your existing JSONL submission history. I'd keep the original hash-based key temporarily if you need backward compatibility, or migrate the history.

## 2. Extract the thread ID

Add:

## 3. Update `parse_html_file()`

After creating the BeautifulSoup object:

Then update the return statement:

## 4. Result

<box border radius="lg" padding={3} gap={2}>
  <text color="secondary" weight="medium" size="xs">Original release title</text>
  `Some Package`
  <divider color="subtle"/>
  <text color="secondary" weight="medium" size="xs">Thread ID</text>
  `1836094`
  <divider color="subtle"/>
  <text color="secondary" weight="medium" size="xs">Unique pyLoad package name</text>
  **Some Package (t1836094)**
</box>

This ensures that two threads with identical release titles receive different pyLoad package names.

**One further recommendation:** keep `release.title` unchanged for GuessIt and resolution filtering, and use `release.package_name` only when submitting to pyLoad or displaying the unique package identity.

Also, even with unique package names, I'd retain `release_keys` in your `pending_containers` mapping. The thread ID is a more reliable identifier for internal bookkeeping than a display name.

## Prompt:

11/11/2026, 7:37:50 PM

ok, but now the process_releases function is never called. instead, my myboerse_release_importer.py script runs this main function:

    def main() -> int:
        p = argparse.ArgumentParser(description=__doc__)
        p.add_argument("--archive", default="archive", help="Directory containing archived thread HTML")
        p.add_argument("--history", default="pyload_added.jsonl", help="JSONL history of successful submissions")
        p.add_argument("--pyload-url", default="http://localhost:9666")
        p.add_argument("--resolution", help="Optional filter, e.g. 720p")
        p.add_argument("--dry-run", action="store_true", help="List candidates without submitting")
        p.add_argument("--passwords", help="Optional archive password string passed to pyLoad")
        p.add_argument("--timeout", type=float, default=15.0)
        p.add_argument("--json-out", help="Write parsed release inventory as JSON")
        p.add_argument("--verbose", action="store_true")

        # parser.add_argument("input_json", type=Path, help="JSON file containing package objects")
        # parser.add_argument("output_json", type=Path, help="Where to write enriched package JSON")
        p.add_argument("--headful", action="store_true", help="Show Firefox and allow manual challenge completion")
        # parser.add_argument("--challenge-timeout", type=int, default=180,
        #                     help="Seconds to wait after you press Enter (default: 180)")
        # parser.add_argument("--log-level", default="INFO",
        #                     choices=("DEBUG", "INFO", "WARNING", "ERROR"))

    args = p.parse_args()
        logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        archive = Path(args.archive).expanduser()
        if not archive.is_dir(): p.error(f"archive directory does not exist: {archive}")
        # Stage 1: parse the entire archive.
        releases = parse_archive(archive)
        LOG.info("Parsed %d releases.", len(releases))
        if args.json_out:
            out = Path(args.json_out).expanduser(); out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps([asdict(r) | {"key": r.key, "package_name": r.package_name} for r in releases], ensure_ascii=False, indent=2), encoding="utf-8")
            LOG.info("Wrote inventory to %s", out)
        # Stage 2: apply customizable filters.
        selected = filter_releases(releases, args)
        LOG.info("%d releases remain after filtering.", len(selected))
        # Stage 3: omit prior successful submissions.
        history_path = Path(args.history).expanduser()
        history = load_history(history_path)
        pending = [r for r in selected if r.key not in history]
        LOG.info("%d releases not in submission history.", len(pending))
        for r in pending: LOG.info("Candidate: %s | GuessIt=%s | links=%s", r.title, r.guessit, ", ".join(r.filecrypt_links))
        if args.dry_run:
            LOG.info("Dry run: nothing submitted."); return 0
        # Stage 4: one pyLoad package per release, log after handler accepts it.
        for r in pending:
            try:
                response = submit_links_to_pyload(r.filecrypt_links, r.package_name, base_url=args.pyload_url,
                                                   passwords=args.passwords, timeout=args.timeout)
            except Exception:
                LOG.exception("Failed to submit %r; it will be retried next run.", r.title); continue
            append_history(history_path, r, response)
            LOG.info("Added to pyLoad: %s", r.title)
        return 0

    if __name__ == "__main__":
        sys.exit(main())

how can i make it use the new process_releases function?

## Response:

11/11/2026, 7:37:52 PM

You only need to make three changes to your existing `main()` function.

## 1. Add the missing command-line arguments

Your `process_releases()` function expects `args.cache_db` and `args.challenge_timeout`, which aren't currently defined.

Add these alongside `--headful`:

## 2. Replace Stage 4 with a call to `process_releases()`

Remove your existing Stage 4:

Replace it with:

Pass `pending` rather than `selected` because you've already filtered out previously submitted releases.

Your `process_releases()` function also checks history internally, which is harmless but redundant.

## 3. Complete updated `main()` function

Here is the complete version, preserving your existing parsing, filtering, history, inventory export, and dry-run functionality.

<CodeBlock language="python" editable>
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)

    p.add_argument("--archive", default="archive",
                   help="Directory containing archived thread HTML")
    p.add_argument("--history", default="pyload_added.jsonl",
                   help="JSONL history of successful submissions")
    p.add_argument("--pyload-url", default="http://localhost:9666")
    p.add_argument("--resolution", help="Optional filter, e.g. 720p")
    p.add_argument("--dry-run", action="store_true",
                   help="List candidates without submitting")
    p.add_argument("--passwords",
                   help="Optional archive password string passed to pyLoad")
    p.add_argument("--timeout", type=float, default=15.0)
    p.add_argument("--json-out",
                   help="Write parsed release inventory as JSON")
    p.add_argument("--verbose", action="store_true")

    # Filecrypt decryption options
    p.add_argument("--headful", action="store_true",
                   help="Show Firefox and allow manual challenges")
    p.add_argument("--challenge-timeout", type=int, default=180,
                   help="Maximum time to wait for a browser challenge")
    p.add_argument("--cache-db", type=Path,
                   default=Path("filecrypt_cache.sqlite3"),
                   help="SQLite cache for decrypted Filecrypt containers")

    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    archive = Path(args.archive).expanduser()

    if not archive.is_dir():
        p.error(f"archive directory does not exist: {archive}")

    # Stage 1: Parse the entire archive.
    releases = parse_archive(archive)
    LOG.info("Parsed %d releases.", len(releases))

    if args.json_out:
        out = Path(args.json_out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)

        out.write_text(
            json.dumps(
                [
                    asdict(r) | {
                        "key": r.key,
                        "package_name": r.package_name,
                    }
                    for r in releases
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        LOG.info("Wrote inventory to %s", out)

    # Stage 2: Apply customizable filters.
    selected = filter_releases(releases, args)

    LOG.info(
        "%d releases remain after filtering.",
        len(selected),
    )

    # Stage 3: Skip previously submitted releases.
    history_path = Path(args.history).expanduser()
    history = load_history(history_path)

    pending = [
        r for r in selected
        if r.key not in history
    ]

    LOG.info(
        "%d releases not in submission history.",
        len(pending),
    )

    for r in pending:
        LOG.info(
            "Candidate: %s | GuessIt=%s | links=%s",
            r.package_name,
            r.guessit,
            ", ".join(r.filecrypt_links),
        )

    if args.dry_run:
        LOG.info("Dry run: nothing submitted.")
        return 0

    # Stage 4: Decrypt containers and submit to pyLoad.
    failures = process_releases(
        pending,
        args,
        history_path,
        history,
    )

    if failures:
        LOG.warning(
            "%d releases failed processing or submission.",
            failures,
        )
        return 1

    LOG.info("All pending releases processed successfully.")
    return 0

if **name** == "**main**":  
sys.exit(main())  
</CodeBlock>

## 4. Run it

The pipeline is now:

`main()` → `process_releases()` → `decrypt_packages()` → SQLite cache → pyLoad → JSONL history.

**One important note:** This assumes you've applied the latest version of `process_releases()` with the single `pending_containers` dictionary and the `iter_pending_packages()` generator.

Also, if you changed `Release.key` from the original SHA-256 hash to `t{thread_id}`, your existing JSONL history won't match those new keys. You'll need to migrate the old history or preserve the old key scheme to avoid resubmitting previously added releases.

------------------------------------------------------------------------

Powered by [ChatGPT Exporter](https://www.chatgptexporter.com)
