#!/usr/bin/env python3

"""
Parse archived MyBoerse and myGully threads and optionally submit downloads to pyLoad.

It recursively parses `*.html` files,
extracts the first bold/strong release title from `.message-body .bbWrapper`,
falls back to the page heading or title,
extracts Rapidgator downloads and Filecrypt containers,
and parses release metadata with GuessIt.
Add custom rules in `filter_releases(releases, args)`.

Each release becomes one pyLoad package named after the parsed title.
Successfully accepted submissions are appended to JSONL history;
matching releases are skipped on later runs.
Failed submissions are not logged and will be retried.
The history confirms pyLoad accepted the handler request, not that the downloads completed.
Review candidates with `--dry-run` before submitting.
Use `--select-link` once per URL to submit only those downloads or containers.
"""

from __future__ import annotations
import os
import sys
import time
import random
import argparse, hashlib, json, logging, re, sys
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse
import sqlite3
from collections.abc import Iterable, Iterator

import requests
from bs4 import BeautifulSoup, Tag
from guessit import guessit

import unicodedata
from rapidfuzz import fuzz, process

sys.path.insert(0, os.path.dirname(__file__) + "/src/filecrypt-scraper-camoufox/src")
from filecrypt_scraper import decrypt_packages, unique

beautifulsoup_html_parser = "html.parser"
import lxml
beautifulsoup_html_parser = "lxml"

LOG = logging.getLogger("myboerse_release_importer")
FILECRYPT_HOSTS = {"filecrypt.cc", "www.filecrypt.cc"}
RAPIDGATOR_HOSTS = {"rapidgator.net", "rg.to"}
RAPIDGATOR_BADGE = "https://i.imgur.com/DrqaS42.png"
DDOWNLOAD_BADGE = "https://i.imgur.com/lQ55QX4.png"

@dataclass
class Release:
    source_file: str
    thread_id: int
    title: str
    title_source: str
    filecrypt_links: list[str]
    guessit: dict[str, Any] = field(default_factory=dict)
    filecrypt_hosters: dict[str, list[str]] = field(default_factory=dict)
    subforum: str | None = None
    direct_links: list[str] = field(default_factory=list)

    @property
    def download_links(self) -> list[str]:
        return self.direct_links + self.filecrypt_links

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


def is_rapidgator_download(url: str) -> bool:
    p = urlparse(url)
    return (
        p.scheme in {"http", "https"}
        and (p.hostname or "").removeprefix("www.") in RAPIDGATOR_HOSTS
        and p.path.startswith("/file/")
        and bool(p.path.removeprefix("/file/"))
    )


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
    h1_tag = soup.select_one(h1_selector) or soup.select_one("h1")
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
        candidate = clean_title(re.sub(r"\s*(?:\|\s*MyBoerse\.bz|-\s*myGully\.com)$", "", full, flags=re.I))
        # print(f"extract_release_title: candidate={candidate!r}")
        if candidate: return candidate, "page-title"
    return None, None

def extract_download_links(soup: Tag) -> tuple[list[str], list[str], dict[str, list[str]]]:
    links: dict[str, set[str]] = {}
    direct_links: dict[str, None] = {}
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if is_rapidgator_download(href):
            direct_links.setdefault(href, None)
            continue
        if not is_filecrypt_container(href):
            continue
        hosters = links.setdefault(href, set())
        badges = {img.get(attr) for img in a.find_all("img") for attr in ("src", "data-url")}
        if DDOWNLOAD_BADGE in badges:
            hosters.add("ddownload.com")
        if RAPIDGATOR_BADGE in badges:
            hosters.add("rapidgator.net")

    for post in soup.select('[id^="post_message_"], .bbWrapper'):
        for node in post.strings:
            if node.find_parent("a"):
                continue
            for match in re.finditer(r"""https?://[^\s<>"']+""", node, flags=re.I):
                url = match.group().rstrip(".,;!)]}")
                if is_rapidgator_download(url):
                    direct_links.setdefault(url, None)
                elif is_filecrypt_container(url):
                    links.setdefault(url, set())

    return list(direct_links), list(links), {
        href: sorted(hosters)
        for href, hosters in links.items()
        if hosters
    }


def extract_subforum(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "DiscussionForumPosting":
            section = data.get("articleSection")
            if isinstance(section, str):
                return section
    breadcrumbs = soup.select('span.smallfont > a[href^="forumdisplay.php?f="]')
    if breadcrumbs:
        return clean_title(breadcrumbs[-1].get_text(" ", strip=True))
    return None


def parse_html_file(path: Path, *, first_post_links: bool = False) -> Release | None:
    # print(f"parse_html_file: path={path!r}")
    try: html = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        LOG.exception("Cannot read %s", path); return None
    soup = BeautifulSoup(html, beautifulsoup_html_parser)
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
    link_scope = soup
    if first_post_links:
        link_scope = next(
            (
                post
                for post in soup.select('article.message--post[data-content^="post-"], table.tborder[id^="post"]')
                if re.fullmatch(
                    r"post-?[0-9]+",
                    post.get("data-content" if post.name == "article" else "id", ""),
                )
            ),
            None,
        )
        if link_scope is None:
            LOG.debug("No first post found in %s", path)
            return None
    direct_links, links, hosters = extract_download_links(link_scope)
    if not title:
        LOG.warning("No release title found in %s", path); return None
    if not links and not direct_links:
        LOG.debug("No supported download links in %s", path); return None
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
        filecrypt_hosters=hosters,
        subforum=extract_subforum(soup),
        direct_links=direct_links,
    )


HTML_PARSER_VERSION = 5
# The cache has one row per file. Use a different version for first-post results.
FIRST_POST_HTML_PARSER_VERSION = -HTML_PARSER_VERSION


def get_cached_release(
        db: sqlite3.Connection,
        path: Path,
        stat: os.stat_result,
        parser_version: int = HTML_PARSER_VERSION,
    ) -> tuple[bool, Release | None]:
    """
    Return (cache_hit, release).

    (False, None): cache miss
    (True, None): cached negative result
    (True, Release): cached release
    """
    row = db.execute(
        """
        SELECT release_json
        FROM html_parse_cache
        WHERE source_file = ?
          AND file_size = ?
          AND file_mtime_ns = ?
          AND parser_version = ?
        """,
        (
            str(path),
            stat.st_size,
            stat.st_mtime_ns,
            parser_version,
        ),
    ).fetchone()

    if row is None:
        return False, None

    if row[0] is None:
        return True, None

    try:
        data = json.loads(row[0])
        return True, Release(**data)
    except (ValueError, TypeError):
        LOG.warning("Invalid HTML cache entry: %s", path)
        return False, None


def cache_parsed_release(
        db: sqlite3.Connection,
        path: Path,
        stat: os.stat_result,
        release: Release | None,
        parser_version: int = HTML_PARSER_VERSION,
    ) -> None:
    db.execute(
        """
        INSERT INTO html_parse_cache (
            source_file,
            file_size,
            file_mtime_ns,
            parser_version,
            release_json,
            cached_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_file) DO UPDATE SET
            file_size = excluded.file_size,
            file_mtime_ns = excluded.file_mtime_ns,
            parser_version = excluded.parser_version,
            release_json = excluded.release_json,
            cached_at = excluded.cached_at
        """,
        (
            str(path),
            stat.st_size,
            stat.st_mtime_ns,
            parser_version,
            (
                json.dumps(asdict(release), ensure_ascii=False)
                if release is not None
                else None
            ),
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def parse_archive(args) -> list[Release]:
    root = Path(args.archive).expanduser()
    subforums = set(args.subforum)
    releases = []
    parser_version = FIRST_POST_HTML_PARSER_VERSION if args.first_post_links else HTML_PARSER_VERSION

    paths = sorted(root.rglob("*.html"))

    debug_stop_after_n_releases = None
    # debug_stop_after_n_releases = 100

    if debug_stop_after_n_releases:
        paths = paths[:debug_stop_after_n_releases]

    ignore_paths = None

    if ignore_paths:
        paths = [
            path for path in paths
            if path not in ignore_paths
        ]

    print(f"parsing HTML files: N={len(paths)}")
    t1 = time.perf_counter()

    hits = 0
    misses = 0
    negative_hits = 0

    cache_path = Path(args.cache_db).expanduser()
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(cache_path) as db:
        init_cache(db)

        for path in paths:
            try:
                stat = path.stat()
            except OSError:
                LOG.exception("Cannot stat %s", path)
                continue

            hit, release = get_cached_release(
                db,
                path,
                stat,
                parser_version,
            )

            if hit:
                hits += 1

                if release is None:
                    negative_hits += 1

            else:
                misses += 1

                release = parse_html_file(path, first_post_links=args.first_post_links)

                # Avoid caching results if the file changed
                # while it was being parsed.
                try:
                    stat_after = path.stat()
                except OSError:
                    LOG.exception("Cannot stat %s after parsing", path)
                    stat_after = None

                if (
                    stat_after is not None
                    and stat_after.st_size == stat.st_size
                    and stat_after.st_mtime_ns == stat.st_mtime_ns
                ):
                    cache_parsed_release(
                        db,
                        path,
                        stat,
                        release,
                        parser_version,
                    )

            if release is not None and (not subforums or release.subforum in subforums):
                releases.append(release)

        # Commit all cache writes in one transaction.
        db.commit()

    dt = time.perf_counter() - t1

    print(
        f"parsing HTML files done: "
        f"dt={dt:.2f}s "
        f"hits={hits} "
        f"misses={misses} "
        f"negative_hits={negative_hits} "
        f"releases={len(releases)}"
    )

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
              "filecrypt_links": release.filecrypt_links, "direct_links": release.direct_links,
              "pyload_response": response,
              "added_at": datetime.now(timezone.utc).isoformat()}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()

def submit_links_to_pyload(links: Sequence[str], package: str, *, base_url: str = "http://localhost:9666",
                           passwords: str | None = None, timeout: float = 60) -> str:
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



@dataclass(frozen=True)
class WantedMovie:
    title: str
    normalized_title: str
    year: int | None
    original_release: str


def normalize_movie_title(title: str) -> str:
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


def load_movie_lists(paths: Sequence[Path]) -> list[WantedMovie]:
    """Load, parse and deduplicate movie entries from multiple files."""
    movies = []
    seen = set()

    for path in paths:
        path = Path(path).expanduser()

        LOG.info("Loading movie list: %s", path)

        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(), 1
        ):
            release_name = line.strip()

            if not release_name or release_name.startswith("#"):
                continue

            try:
                parsed = guessit(
                    release_name,
                    options={"type": "movie"},
                )

                title = str(parsed.get("title", "")).strip()
                year = parsed.get("year")

                if not title:
                    LOG.warning(
                        "No movie title in %s:%d: %s",
                        path, line_number, release_name,
                    )
                    continue

                normalized = normalize_movie_title(title)
                if not normalized:
                    continue

                # year = int(year) if year is not None else None
                if isinstance(year, list):
                    # the parser found multiple years
                    # use the first year
                    year = year[0]
                if isinstance(year, str):
                    year = int(year)

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
                    "Failed parsing movie in %s:%d: %s",
                    path, line_number, release_name,
                )

    LOG.info(
        "Loaded %d unique movies from %d files",
        len(movies),
        len(paths),
    )

    return movies


def find_wanted_movie(
        release: Release,
        wanted_movies: list[WantedMovie],
        threshold: float = 90.0,
    ) -> tuple[WantedMovie, float] | None:
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


def filter_releases(
        releases: list[Release],
        args,
    ) -> list[Release]:
    selected = releases

    if args.filehoster or args.select_link:
        selected_urls = set(args.select_link)
        selected = []
        for release in releases:
            links = [
                url for url in release.filecrypt_links
                if (not selected_urls or url in selected_urls)
                and (not args.filehoster or not release.filecrypt_hosters.get(url)
                     or args.filehoster in release.filecrypt_hosters[url])
            ]
            direct_links = [
                url for url in release.direct_links
                if (not selected_urls or url in selected_urls)
                and args.filehoster in (None, "rapidgator.net")
            ]
            if links or direct_links:
                selected.append(replace(
                    release,
                    direct_links=direct_links,
                    filecrypt_links=links,
                    filecrypt_hosters={
                        url: release.filecrypt_hosters[url]
                        for url in links
                        if url in release.filecrypt_hosters
                    },
                ))

    if not selected:
        print(f"filter_releases: empty input")
        return selected

    if 0:
        # debug
        for release in selected:
            print(f"filter_releases: release={release}")
            sys.exit()

    # filter by thread author
    # if args.author_id:

    if args.release_group:
        wanted_release_group = args.release_group.casefold()
        selected = [
            release for release in selected
            if release.guessit.get("release_group", "").casefold() == wanted_release_group
        ]
        print(f"filter_releases: {len(releases)} releases remain after filtering by release group")
        if not selected:
            return selected

    if args.resolution:
        # filter by video resolution
        wanted_resolution = args.resolution.casefold()
        selected = [
            release for release in selected
            if (
                str(release.guessit.get("screen_size", "")).casefold() == wanted_resolution
                or wanted_resolution in release.title.casefold()
            )
        ]
        print(f"filter_releases: {len(releases)} releases remain after filtering by resolution")
        if not selected:
            return selected

    # Load and deduplicate both movie lists.
    wanted_movies = load_movie_lists(args.wanted_movies)
    unwanted_movies = load_movie_lists(args.unwanted_movies)

    LOG.info(
        "Movie filters: wanted=%d, unwanted=%d",
        len(wanted_movies),
        len(unwanted_movies),
    )

    filtered = []

    for release in selected:

        # Step 1: Whitelist.
        # If whitelist files were provided, a match is required.
        if args.wanted_movies:
            wanted_match = find_wanted_movie(
                release,
                wanted_movies,
                threshold=args.movie_match_threshold,
            )

            if wanted_match is None:
                continue

        # Step 2: Blacklist.
        # Blacklist always takes precedence.
        if unwanted_movies:
            unwanted_match = find_wanted_movie(
                release,
                unwanted_movies,
                threshold=args.movie_match_threshold,
            )

            if unwanted_match is not None:
                movie, score = unwanted_match

                LOG.info(
                    "BLACKLISTED (%.1f%%): %s -> %s (%s)",
                    score,
                    release.title,
                    movie.title,
                    movie.year,
                )
                continue

        # Release passed both filters.
        if args.wanted_movies:
            movie, score = wanted_match

            LOG.info(
                "WANTED (%.1f%%): %s -> %s (%s)",
                score,
                release.title,
                movie.title,
                movie.year,
            )

        filtered.append(release)

    print(f"filter_releases: {len(filtered)} releases remain after filtering by wanted and unwanted movies")
    if not filtered:
        return filtered
    LOG.info(f"Movie filtering: {len(selected)} -> {len(filtered)} releases")
    selected = filtered

    return selected


def init_cache(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS filecrypt_cache (
            url TEXT PRIMARY KEY,
            decrypted_urls TEXT NOT NULL,
            cached_at TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS html_parse_cache (
            source_file TEXT PRIMARY KEY,
            file_size INTEGER NOT NULL,
            file_mtime_ns INTEGER NOT NULL,
            parser_version INTEGER NOT NULL,
            release_json TEXT,
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
    urls = [url for url in unique(urls) if is_rapidgator_download(url)]

    if not urls:
        raise ValueError(
            f"No Rapidgator download links for {release.title}"
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

            # print(f"release {release}"); sys.exit() # debug

            state = {
                "release": release,
                "urls": list(release.direct_links),
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

        # Submit direct and fully cached releases without starting Firefox.
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


def normalize_filehoster(value: str) -> str:
    host = value.strip().casefold().removeprefix("www.")
    return {
        "rapidgator": "rapidgator.net",
        "rg.to": "rapidgator.net",
        "ddownload": "ddownload.com",
        "ddl.to": "ddownload.com",
    }.get(host, host)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", default="archive", help="Directory containing archived thread HTML")
    p.add_argument(
        "--forum",
        metavar="DOMAIN",
        help="Read archived thread HTML from this domain's subdirectory under --archive",
    )
    p.add_argument("--history", default="pyload_added.jsonl", help="JSONL history of successful submissions")
    p.add_argument("--pyload-url", default="http://localhost:9666")
    p.add_argument(
        "--first-post-links",
        action="store_true",
        help="Extract download links only from the first post in each archived thread",
    )
    p.add_argument("--resolution", help="Optional filter, e.g. 720p")
    p.add_argument("--release-group", help="Filter by release group name")
    p.add_argument(
        "--subforum",
        nargs="+",
        action="extend",
        default=[],
        metavar="NAME",
        help="Filter by one or more exact subforum names",
    )
    p.add_argument(
        "--filehoster",
        type=normalize_filehoster,
        help="Keep links for this host (e.g. rapidgator.net) and Filecrypt containers with an unknown host",
    )
    p.add_argument(
        "--select-link",
        action="append",
        default=[],
        metavar="URL",
        help="Keep this exact download or container URL (repeat for multiple URLs)",
    )
    p.add_argument("--dry-run", action="store_true", help="List candidates without submitting")
    p.add_argument("--passwords", help="Optional archive password string passed to pyLoad")
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--json-out", help="Write parsed release inventory as JSON")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Limit the number of releases to process after filtering")
    p.add_argument("--headful", action="store_true", help="Show Firefox and allow manual challenge completion")
    p.add_argument("--shuffle", action="store_true", help="Process releases in random order")
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
    p.add_argument(
        "--wanted-movies",
        type=Path,
        nargs="+",
        action="extend",
        default=[],
        metavar="FILE",
        help="One or more text files containing wanted movie release names",
    )

    p.add_argument(
        "--unwanted-movies",
        type=Path,
        nargs="+",
        action="extend",
        default=[],
        metavar="FILE",
        help="One or more text files containing movies to exclude",
    )
    p.add_argument(
        "--movie-match-threshold",
        type=float,
        default=90.0,
        help="Minimum fuzzy movie title similarity (0-100, default: 90)",
    )
    args = p.parse_args()
    if args.forum is not None:
        if not re.fullmatch(r"[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+", args.forum):
            p.error("--forum must be a domain name (e.g. mygully.com)")
        args.archive = str(Path(args.archive).expanduser() / args.forum)
    # print(f"args={args}")
    for key, val in args.__dict__.items():
        print(f"args.{key}={val!r}")
    if not 0 <= args.movie_match_threshold <= 100:
        p.error("--movie-match-threshold must be between 0 and 100")
    for label, paths in (
        ("--wanted-movies", args.wanted_movies),
        ("--unwanted-movies", args.unwanted_movies),
    ):
        for path in paths:
            if not path.expanduser().is_file():
                p.error(f"{label}: file does not exist: {path}")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    archive = Path(args.archive).expanduser()
    if not archive.is_dir(): p.error(f"archive directory does not exist: {archive}")
    # Stage 1: parse the entire archive.
    releases = parse_archive(args)
    if args.select_link:
        available_urls = {url for release in releases for url in release.download_links}
        missing_urls = [url for url in args.select_link if url not in available_urls]
        if missing_urls:
            p.error("selected URLs not found in parsed releases: " + ", ".join(missing_urls))
    if args.shuffle:
        # process releases in random order
        random.shuffle(releases)
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
    if args.limit and args.limit < len(pending):
        print(f"limiting pending releases from {len(pending)} to {args.limit}")
        pending = pending[:args.limit]
    for r in pending: LOG.info("Candidate: %s | GuessIt=%s | links=%s", r.title, r.guessit, ", ".join(r.download_links))
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
