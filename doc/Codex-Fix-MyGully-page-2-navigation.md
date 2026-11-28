# Fix MyGully page 2 navigation

> fix the scraper for mygully.com
>
> currently the scraper fails to navigate to page 2 of the subforum:
>
> ```
> 2026-11-28 17:01:44,208 INFO Subforum page: https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/?pp=50&daysprune=-1&prefixid=SachbuchEbooks
> 2026-11-28 17:01:46,546 INFO Downloading thread 6453950: https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/showthread.php?t=6453950
> 2026-11-28 17:01:51,015 INFO Downloading thread 8685571: https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/showthread.php?t=8685571
> 2026-11-28 17:01:54,750 INFO Downloading thread 8750645: https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/showthread.php?t=8750645
> ...
> 2026-11-28 17:04:58,514 INFO Subforum page: https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/forumdisplay.php?f=104&pp=50&prefixid=SachbuchEbooks&order=desc&daysprune=-1&page=2
> 2026-11-28 17:05:01,942 ERROR MyGully redirected to a different listing page: https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele-2/?pp=50&prefixid=SachbuchEbooks&daysprune=-1
> ```
>
> the scraper should just follow the redirect. apparently [`https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/`](https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/) is page 1, and [`https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele-2/`](https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele-2/) is page 2 of the subforum

<details><summary>2 previous messages</summary>

> I’ll trace how the scraper validates MyGully redirects and check that it recognizes the page number in the redirected URL.
>
> <details><summary>Edited a file, explored a list, ran 4 commands, searched the web</summary>
>
> - Ran `git status --short; rg -n 'different listing page|MyGully'; rg --files -g AGENTS.md -g '*test*'`
>
> <details><summary>Explored a list</summary>
>
> - Listed files
>
> </details>
>
> Searched the web for `https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele-2/`
>
> - Ran `sed -n '1,140p' myboerse_scraper.py; for f in AGENTS.md ../AGENTS.md ../../AGENTS.md; do if test -f "$f"; then cat "$f"; fi; done`
>
> - Wrote `./myboerse_scraper.py` (+10 -2)
>
> - Ran `python3 -B -c 'import myboerse_scraper'; git diff --check`
>
> - Ran `python3 -B - <<'PY'
> import asyncio
> from pathlib import Path
> from tempfile import TemporaryDirectory
> from types import SimpleNamespace
> from myboerse_scraper import scrape_mygully_subforum
>
> base = "https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele"
> filters = "pp=50&daysprune=-1&prefixid=SachbuchEbooks"
> start = f"{base}/?{filters}"
> legacy = f"{base}/forumdisplay.php?f=104&page=2"
> request_two = f"{base}/forumdisplay.php?f=104&page=2&{filters}"
> canonical = f"{base}-2/?{filters}"
>
> class Page:
>     def __init__(self):
>         self.visited = []
>
>     async def goto(self, url, **kwargs):
>         self.visited.append(url)
>         self.url = canonical if url == request_two else url
>         return SimpleNamespace(ok=True)
>
>     def locator(self, selector):
>         return self
>
>     async def count(self):
>         return 1
>
>     async def evaluate_all(self, _):
>         if self.url == start:
>             return [legacy, f"{base}/showthread.php?t=101"]
>         return [f"{base}/showthread.php?t=102"]
>
>     async def content(self):
>         return "<html></html>"
>
> with TemporaryDirectory() as directory:
>     output = Path(directory)
>     page = Page()
>     asyncio.run(scrape_mygully_subforum(page, start, output, 0))
>     assert page.visited == [start, f"{base}/showthread.php?t=101", request_two, f"{base}/showthread.php?t=102"], page.visited
>     assert sorted(p.name for p in output.iterdir()) == ["101.html", "102.html"]
> print("Mocked page 2 redirect and thread downloads passed")
> PY
> git diff --check`
>
> </details>
</details>

Fixed MyGully pagination in [myboerse_scraper.py](./myboerse_scraper.py:77). The scraper now recognizes `?page=2` and the canonical `-2/` URL as the same page, so it continues scraping after the redirect.

A mocked scrape verified that the request retained the filters and that threads were saved from both pages. Live MyGully behavior remains unverified.
