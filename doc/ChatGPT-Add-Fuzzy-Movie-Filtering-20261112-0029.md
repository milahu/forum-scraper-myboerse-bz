# Add Fuzzy Movie Filtering

**User:** Anonymous  
**Created:** 2026/11/11 21:10:32  
**Updated:** 2026/11/11 22:42:12  
**Exported:** 2026/11/12 0:29:49  
**Link:** [<https://chatgpt.com/c/6af4cbb8-0a18-83ed-b56a-9bd585042d3e>](https://chatgpt.com/c/6af4cbb8-0a18-83ed-b56a-9bd585042d3e)

## Prompt:

11/11/2026, 9:13:50 PM

help me to add a feature to my python script

the script already does this: parse packages with download links from HTML files, scrape the actual download links from filecrypt.cc containers, add the actual download links to pyLoad

now the new feature i need is this: i want to filter the packages by movie names using the `guessit` library to parse filesharing release names. i have a text file like `wanted-movie-names.txt`

    Tar.2022.German.800p.microHD.x264-RAIST
    Sentimental.Value.2025.German.1040p.microHD.x264-RAIST
    S.Darko.-.Eine.Donnie.Darko.Saga.2009.German.1040p.microHD.x264-RAIST
    Poor.Things.2023.German.1080p.microHD.x264-RAIST
    Ohne.Limit.2011.German.800p.microHD.x264-RAIST

which i want to parse to extract a list of "wanted movie names".

then i want to filter the packages to download, to process only the packages whose parsed movie name exists in the list of "wanted movie names".

the raw packages to download have release names like

``` css
Agents.of.SHIELD.S01-S07.COMPLETE.GERMAN.AC3.720p.BluRay+WEB.x265-w00t
Anna.2019.GERMAN.AAC.1080p.UHD.BluRay.HDR.x265-w00t
A.Beautiful.Mind.2001.GERMAN.AAC.1080p.UHD.BluRay.HDR.x265-w00t
Eternauta.S01.GERMAN.AAC.1080p.WEB.x265-w00t
Star.Trek.Short.Treks.S01.GERMAN.AAC.1080p.WEB.x265-w00t
Lawmen.Bass.Reeves.S01.GERMAN.AAC.1080p.WEB.x265-w00t
Eternals.2021.GERMAN.AC3.2160p.UHD.BluRay.HDR.x265-w00t
Scrubs.2026.S01.GERMAN.AAC.720p.WEB.x265-w00t
Atlanta.S01-S04.COMPLETE.GERMAN.AAC.720p.WEB.x265-w00t
Ein.Minecraft.Film.2025.GERMAN.AAC.1080p.UHD.BluRay.HDR.x265-w00t
Barbie.2023.GERMAN.AAC.1080p.UHD.BluRay.HDR.x265-w00t
Der.Exorzist.EXTENDED.1973.GERMAN.AAC.1080p.UHD.BluRay.HDR.x265-w00t
Bodyguard.S01.GERMAN.AC3.1080p.BluRay.x265-w00t
A.Million.Little.Things.S01.GERMAN.AC3D.720p.WEB.x265-w00t
John.Wick.Kapitel.2.2017.GERMAN.AAC.2160p.UHD.BluRay.HDR.x265-w00t
```

i guess the challenge here is to use fuzzy matching to tolerate slight variations in punctuation

here is my python script i want to modify:

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
import os
import sys
import time
import argparse, hashlib, json, logging, re, sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse
import sqlite3
from collections.abc import Iterable, Iterator

import requests
from bs4 import BeautifulSoup
from guessit import guessit

sys.path.insert(0, os.path.dirname(__file__) + "/src/filecrypt-scraper-camoufox/src")
from filecrypt_scraper import decrypt_packages, unique

LOG = logging.getLogger("myboerse_release_importer")
FILECRYPT_HOSTS = {"filecrypt.cc", "www.filecrypt.cc"}

@dataclass
class Release:
    source_file: str
    thread_id: int
    title: str
    title_source: str
    filecrypt_links: list[str]
    guessit: dict[str, Any] = field(default_factory=dict)
    @property
    def key(self) -> str:
        return f"t{self.thread_id}"
    @property
    def package_name(self) -> str:
        return f"{self.title.strip()} (t{self.thread_id})"

def clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n|")

def is_filecrypt_container(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in {"http", "https"} and (p.hostname or "").lower() in FILECRYPT_HOSTS and "/container/" in p.path.lower()

def extract_thread_id(path: Path, soup: BeautifulSoup) -> int | None:
    # Primary source: HTML filename, e.g. 1836094.html
    filename_id = (
        int(path.stem)
        if path.stem.isdecimal()
        else None
    )

    # Secondary source: <html data-content-key="thread-1836094">
    html_tag = soup.find("html")
    content_key = (
        html_tag.get("data-content-key", "")
        if html_tag
        else ""
    )

    match = re.fullmatch(r"thread-(\d+)", content_key)
    content_id = int(match.group(1)) if match else None

    if filename_id is not None and content_id is not None:
        if filename_id != content_id:
            raise ValueError(
                f"Thread ID mismatch in {path}: "
                f"filename={filename_id}, HTML={content_id}"
            )

    return filename_id if filename_id is not None else content_id

def extract_release_title(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    # articles container:
    # /html/body/div[1]/div[4]/div/div[4]/div[2]/div/div[3]/div[3]/div
    # <div class="p-body-content"
    #  <div class="p-body-pageContent"
    #   <div class="block block--messages"
    #    <div class="block-container lbContainer"
    #     <div class="block-body js-replyNewMessageContainer">
    # article element:
    # <article class="message message--post js-post js-inlineModContainer  " id="js-post-5913241"
    #  <div class="message-inner"
    #   <div class="message-cell message-cell--main"
    #    <div class="message-main js-quickEditTarget"
    #     <div class="message-content js-messageContent"
    #      <div class="message-userContent lbContainer js-lbContainer "
    #       <article class="message-body js-selectToQuote"
    #        <div>
    #         <div class="bbWrapper"

    # NOTE use only the first article element = first post in the thread
    # other posts are "reups" = reuploads of the same content by different users
    bold_selector = "div.block-body > article.message:nth-child(1) > div.message-inner > div.message-cell > div.message-main > div.message-content > div.message-userContent > article.message-body > div:nth-child(1) > div.bbWrapper b:nth-child(1)"
    for node in soup.select(bold_selector):
        # print(f"extract_release_title: node.name={node.name}")
        # print(f"extract_release_title: node:\n{node}")
        # if node.name not in ("b", "strong"): continue
        # print(f"extract_release_title: node.get_text: " + repr(node.get_text(" ", strip=True)))
        candidate = clean_title(node.get_text(" ", strip=True))
        # print(f"extract_release_title: candidate={candidate!r}")
        if candidate and len(candidate) >= 3 and not re.search(r"^(?:download|screenshots?|nfo|mediainfo|passwort|password)\s*:?$", candidate, re.I):
            return candidate, "message-bold"

    # <h1 class="p-title-value">Some Title</h1>
    h1_selector = "h1.p-title-value"
    h1_tag = soup.select_one(h1_selector)
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
    thread_id = extract_thread_id(path, soup)
    if thread_id is None:
        LOG.warning("No thread ID found in %s", path)
        return None
    title, source = extract_release_title(soup)
    bad_titles = (
        "bitte löschen",
    )
    if title in bad_titles: return None
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
    # print(f"parse_html_file: path={path} title={title!r}")
    return Release(
        source_file=str(path),
        thread_id=thread_id,
        title=title,
        title_source=source or "unknown",
        filecrypt_links=links,
        guessit=guessit_data,
    )

def parse_archive(root: Path) -> list[Release]:
    releases = []

    debug_stop_after_n_releases = None
    # debug_stop_after_n_releases = 10
    n = 0

    paths = sorted(root.rglob("*.html"))
    # paths = [Path("archive/myboerse/1636873.html")] # debug: "bitte löschen"
    # paths = [Path("archive/myboerse/2868879.html")] # debug: "Haunted.Hotel.S02.GERMAN.AAC.720p.WEB.x265-w00t"

    # paths = paths[:100] # debug: use only the first 100 HTML files

    # TODO cache results from parse_html_file
    print(f"parsing HTML files: N={len(paths)}")
    t1 = time.time()

    ignore_paths = (
        # FIXME requests.post throws ConnectionError on too many links
        # 651 links
        # Akte.X.S01-S11.COMPLETE.GERMAN.AC3.720p.BluRay.x265-w00t
        Path("archive/myboerse/1267794.html"),
    )

    for path in paths:
        if path in ignore_paths:
            continue
        release = parse_html_file(path)
        if release: releases.append(release)
        if debug_stop_after_n_releases and release:
            n += 1
            if n > debug_stop_after_n_releases:
                break

    t2 = time.time()
    print(f"parsing HTML files done: dt={(t2 - t1):.2f}")

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
            except json.JSONDecodeError as exc: LOG.warning(f"Ignoring malformed history file {path} line {n}: {type(exc).__name__}: {exc}")
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
    print(f"adding links to pyload: N={len(links)}")
    # adding links to pyload: N=651
    # pyload  addon ClickNLoad: Connection from 127.0.0.1:58136
    # pyload  Added package Akte.X.S01-S11.COMPLETE.GERMAN.AC3.720p.BluRay.x265-w00t (t1267794) containing 651 links
    # FIXME requests.post throws ConnectionError on too many links
    timeout=(5, 120) # 5 seconds is the connection timeout and 120 seconds is the read timeout
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
    if args.
    return selected

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
    ) -> list[str] | None:
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
        urls: list[str],
    ) -> None:
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

def submit_resolved_release(
        release: Release,
        urls: list[str],
        args,
        history_path: Path,
        history: dict,
    ) -> None:
    urls = unique(urls)

    # filter URLs by hoster
    def filter_fn(url):
        return url.lower().startswith("https://rapidgator.net/")
    urls = list(filter(filter_fn, urls))

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

        # we want to decrypt each container only once
        # so we use container_url as the key for containers_to_decrypt
        # containers_to_decrypt[container_url] = entry
        # and each entry can have multiple package_names
        #
        # ideally, every container should have only one package
        # but in the real world, the input data can be inconsistent
        # so multiple packages can share the same container_url
        containers_to_decrypt = {}

        for release in releases:
            if release.key in history or release.key in states:
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

                entry = containers_to_decrypt.setdefault(
                    container_url,
                    {
                        "package_names": [],
                        "release_keys": [],
                    },
                )

                entry["package_names"].append(release.package_name)
                entry["release_keys"].append(release.key)

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

        if not containers_to_decrypt:
            LOG.info("No containers need decryption")
            return failures

        def iter_containers_to_decrypt():
            for container_url, entry in containers_to_decrypt.items():
                yield {
                    "name": entry["package_names"][0],
                    "filecrypt_url": container_url,
                }

        # The generator starts Camoufox once (decrypt_packages) and reuses its page.
        for result in decrypt_packages(iter_containers_to_decrypt(), args):
            container_url = result["filecrypt_url"]
            entry = containers_to_decrypt[container_url]

            # # Process result and update containers_to_decrypt.
            # release_key = result["release_key"]
            # state = states[release_key]
            # container_url = result["filecrypt_url"]

            error = result.get("decryption_error")
            urls = result.get("decrypted_urls", [])

            # if error or not urls:
            #     state["failed"] = True
            #     LOG.error("Failed container %s: %s", container_url, error or "No URLs")
            # else:
            #     # Persist immediately, before processing the next container.
            #     try:
            #         cache_decrypted_urls(db, container_url, urls)
            #         state["urls"].extend(urls)
            #     except Exception:
            #         state["failed"] = True
            #         LOG.exception("Could not cache %s", container_url)

            if not error and urls:
                try:
                    cache_decrypted_urls(db, container_url, urls)
                except Exception as exc:
                    LOG.exception("Cache write failed: %s", container_url)
                    error = f"Cache write failed: {exc}"
            else:
                error = error or "No decrypted URLs"

            for release_key in entry["release_keys"]:
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
                    LOG.warning("Skipping incomplete release %s", state["release"].title)
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
                    LOG.exception("Failed submitting %s", state["release"].title)

    return failures

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
    p.add_argument("--limit", type=int, default=0, help="Limit the number of releases to process after filtering")
    p.add_argument("--headful", action="store_true", help="Show Firefox and allow manual challenge completion")
    p.add_argument(
        "--cache-db",
        type=Path,
        default=Path("filecrypt_cache.sqlite3"),
        help="SQLite cache for decrypted Filecrypt containers",
    )
    p.add_argument(
        "--challenge-timeout",
        type=int,
        default=180,
        help="Maximum time to wait for a browser challenge",
    )
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
    if args.limit and args.limit > len(pending):
        print(f"limiting pending releases from {len(pending)} to {args.limit}")
        pending = pending[:args.limit]
    LOG.info("%d releases not in submission history.", len(pending))
    for r in pending: LOG.info("Candidate: %s | GuessIt=%s | links=%s", r.title, r.guessit, ", ".join(r.filecrypt_links))
    if args.dry_run:
        LOG.info("Dry run: nothing submitted."); return 0
    r'''
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
    '''
    # Stage 4: decrypt Filecrypt containers (with SQLite caching)
    # and submit resolved releases to pyLoad.
    failures = process_releases(
        pending,
        args,
        history_path,
        history,
    )
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
```

## Response:

11/11/2026, 9:13:57 PM

> **Testing GuessIt Media Filename Parsing**
>
> **Tested GuessIt media filename parsing**
>
> Worked for 10s

I would implement this as a **movie-title whitelist filter**, using `guessit` to extract movie titles and `rapidfuzz` to tolerate small differences in punctuation, spacing, and spelling.

The nice thing is that your script already has the right architecture: `filter_releases()` runs before Filecrypt decryption, caching, and pyLoad submission. We can add the new feature without changing any of those stages.

## 1. Matching strategy

I recommend three steps:

1.  **Parse titles with GuessIt.** Extract `title` from both `wanted-movie-names.txt` and your archived releases, forcing `type="movie"` for the wanted entries.
2.  **Normalize titles.** Ignore capitalization, punctuation, separators, and accents.
3.  **Match exact titles first, then fuzzy titles.** Use RapidFuzz with a configurable similarity threshold, defaulting to `90`.

For example:

| Wanted release | Parsed movie title |
|----|----|
| `Tar.2022.German.800p.microHD.x264-RAIST` | Tar |
| `Sentimental.Value.2025.German.1040p.microHD.x264-RAIST` | Sentimental Value |
| `S.Darko.-.Eine.Donnie.Darko.Saga.2009...` | S Darko - Eine Donnie Darko Saga |
| `Poor.Things.2023.German.1080p...` | Poor Things |
| `Ohne.Limit.2011.German.800p...` | Ohne Limit |

One important safeguard: **don't use fuzzy matching to override conflicting movie years**. A release with the same title but a different known year should not automatically match.

Also, exclude TV releases using GuessIt's `type` field. Otherwise a movie whitelist could accidentally match a television series with the same name.

## 2. Install RapidFuzz

You already have `guessit`, so you only need one additional dependency:

## 3. Add the matching functions

Add these imports near the top of your script:

Then add the following functions before `filter_releases()`:

<CodeBlock language="python" editable>
@dataclass(frozen=True)
class WantedMovie:
    title: str
    normalized_title: str
    year: int | None
    original_release: str

def normalize_movie_title(title: str) -\> str:  
"""Normalize movie titles for punctuation-insensitive matching."""  
title = unicodedata.normalize("NFKD", title.casefold())

    # Remove accents, e.g. "Amélie" -> "amelie".
    title = "".join(
        c for c in title
        if not unicodedata.combining(c)
    )

    # Treat punctuation and separators as spaces.
    title = re.sub(r"[^a-z0-9]+", " ", title)

    return " ".join(title.split())

def load_wanted_movies(path: Path) -\> list\[WantedMovie\]:  
"""Parse the wanted release names into movie titles."""  
movies = \[\]  
seen = set()

    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        release_name = line.strip()

        if not release_name or release_name.startswith("#"):
            continue

        try:
            # Force movie parsing for the wanted list.
            parsed = guessit(
                release_name,
                options={"type": "movie"},
            )

            title = str(parsed.get("title", "")).strip()
            year = parsed.get("year")

            if not title:
                LOG.warning(
                    "No movie title on line %d: %s",
                    line_number, release_name,
                )
                continue

            normalized = normalize_movie_title(title)
            if not normalized:
                continue

            year = int(year) if year is not None else None
            key = (normalized, year)

            if key in seen:
                continue

            seen.add(key)

            movies.append(WantedMovie(
                title=title,
                normalized_title=normalized,
                year=year,
                original_release=release_name,
            ))

        except Exception:
            LOG.exception(
                "Failed parsing wanted movie on line %d: %s",
                line_number, release_name,
            )

    LOG.info("Loaded %d wanted movies from %s", len(movies), path)
    return movies

def find_wanted_movie(  
release: Release,  
wanted_movies: list\[WantedMovie\],  
threshold: float = 90.0,  
) -\> tuple\[WantedMovie, float\] \| None:  
"""Return the best matching wanted movie and similarity score."""

    metadata = release.guessit

    # Reject TV series.
    if str(metadata.get("type", "")).casefold() == "episode":
        return None

    # Also reject releases containing season/episode metadata.
    if "season" in metadata or "episode" in metadata:
        return None

    title = str(metadata.get("title", "")).strip()
    if not title:
        return None

    normalized = normalize_movie_title(title)
    if not normalized:
        return None

    raw_year = metadata.get("year")
    release_year = int(raw_year) if raw_year is not None else None

    # Only compare movies with compatible years.
    candidates = [
        movie for movie in wanted_movies
        if (
            release_year is None
            or movie.year is None
            or release_year == movie.year
        )
    ]

    if not candidates:
        return None

    # Fast path: exact normalized title match.
    for movie in candidates:
        if normalized == movie.normalized_title:
            return movie, 100.0

    # Fuzzy path: find best title similarity.
    result = process.extractOne(
        normalized,
        [movie.normalized_title for movie in candidates],
        scorer=fuzz.ratio,
        score_cutoff=threshold,
    )

    if result is None:
        return None

    _, score, index = result
    return candidates[index], score

</CodeBlock>

### Why `fuzz.ratio` instead of `fuzz.token_set_ratio`?

For your use case, `fuzz.ratio` is a safer default.

Consider these two titles:

- `John Wick`
- `John Wick Kapitel 2`

`token_set_ratio` can assign a perfect score when one title's tokens are contained in the other. That is dangerous for movie matching because it can confuse sequels with their originals.

`fuzz.ratio` penalizes the additional words, reducing false positives.

Normalization already handles the punctuation differences you care about, so you shouldn't need especially aggressive fuzzy matching.

## 4. Replace `filter_releases()`

Replace your incomplete function with:

<CodeBlock language="python" editable>
def filter_releases(
    releases: list[Release],
    args,
) -> list[Release]:
    selected = releases

    # Existing resolution filter.
    if args.resolution:
        wanted = args.resolution.casefold()
        selected = [
            r for r in selected
            if (
                str(r.guessit.get("screen_size", "")).casefold()
                == wanted
                or wanted in r.title.casefold()
            )
        ]

    # New wanted-movie filter.
    if args.wanted_movies:
        wanted_movies = load_wanted_movies(
            Path(args.wanted_movies).expanduser()
        )

        if not wanted_movies:
            LOG.warning("Wanted movie list is empty")
            return []

        matched = []

        for release in selected:
            result = find_wanted_movie(
                release,
                wanted_movies,
                threshold=args.movie_match_threshold,
            )

            if result is None:
                continue

            movie, score = result

            LOG.info(
                "Movie match (%.1f%%): %s -> %s (%s)",
                score,
                release.title,
                movie.title,
                movie.year,
            )

            matched.append(release)

        selected = matched

        LOG.info(
            "Wanted movie filter: %d matching releases",
            len(selected),
        )

    return selected

</CodeBlock>

This implementation preserves your existing resolution filter. Both filters are combined with logical AND when both options are provided.

## 5. Add CLI arguments

In `main()`, add these arguments before `args = p.parse_args()`:

Also add validation immediately after `args = p.parse_args()`:

## 6. Run the script

First, test with a dry run:

For more permissive fuzzy matching:

And to combine with your existing resolution filter:

When you're satisfied with the matches, remove `--dry-run` to process them normally.

## 7. Example matching behavior

These are illustrative outcomes, assuming GuessIt extracts the expected movie titles.

| Wanted movie | Archived release title | Result |
|----|----|----|
| `Poor Things (2023)` | `Poor.Things.2023.GERMAN.1080p...` | <badge color="success">Match</badge> |
| `Ohne Limit (2011)` | `Ohne-Limit.2011.720p...` | <badge color="success">Match</badge> |
| `Sentimental Value (2025)` | `Sentimental_Value_2025...` | <badge color="success">Match</badge> |
| `Poor Things (2023)` | `Poor.Things.2024...` | <badge>Rejected: year</badge> |
| `Poor Things (2023)` | `Poor.Things.S01...` | <badge>Rejected: TV</badge> |
| `John Wick (2014)` | `John.Wick.Kapitel.2.2017...` | <badge>Rejected: year</badge> |

## 8. Two improvements I'd consider

**First: make movie parsing explicit in `parse_html_file()`.**

Your existing code calls:

I would keep this unchanged for now. GuessIt needs to detect TV releases so we can exclude them.

For wanted-list entries, however, forcing movie parsing makes sense because that file explicitly contains movies.

**Second: add an optional fuzzy-match report.**

A threshold of 90 is conservative, but not perfect. Some localized movie titles can be significantly different from their international equivalents, and punctuation normalization won't solve that.

For example, `Ohne Limit` and `Limitless` refer to the same movie, but their titles have very low string similarity. Matching those requires an alias database, not fuzzy matching alone.

------------------------------------------------------------------------

### One important detail about your existing script

I noticed an unrelated bug in the `--limit` implementation:

This condition is reversed. It should be:

Otherwise `--limit 10` won't restrict a list of 100 pending releases.

**My recommendation:** Start with a fuzzy threshold of `90`, require matching years whenever both are known, and inspect the dry-run results. This gives you a conservative movie whitelist that integrates directly into your existing importer without touching the Filecrypt or pyLoad logic.

------------------------------------------------------------------------

Powered by [ChatGPT Exporter](https://www.chatgptexporter.com)
