# Switch scraper to Camoufox

> rewrite this webscraper to use camoufox instead of patchright

<details><summary>4 previous messages</summary>

> I’ll check how the scraper uses Patchright, then update the browser integration and verify what I can locally.
>
> <details><summary>Edited 4 files, explored a file, a search, 2 lists, ran 6 commands, searched the web</summary>
>
> - Ran `mkdir -p /tmp/nix-shell-3905490-1256608070 && git status --short && rg --files | head -80`
>
> - Ran `cat requirements.txt shell.nix && sed -n '1,125p' myboerse_scraper.py`
>
> <details><summary>Explored a search, a list</summary>
>
> - Searched for `patchright|playwright|chromium|cloudflare|captcha|stealth|camoufox` in `myboerse_scraper.py`
> - Listed files
>
> </details>
>
> Searched the web for `Camoufox official Python AsyncCamoufox async api headless python -m camoufox fetch`
>
> - Ran `sed -n '185,355p' myboerse_scraper.py && cat readme.md && ls -la .. | head -30 && python3 -m pip show camoufox playwright`
>
> - Ran `for p in ../AGENTS.md ../../AGENTS.md ./AGENTS.md; do if test -f "$p"; then cat "$p"; fi; done
> python3 -c 'from camoufox.async_api import AsyncCamoufox; from playwright.async_api import TimeoutError; import inspect; print(inspect.getsource(AsyncCamoufox))'
> command -v nix-shell
> rg -ni 'patchright|camoufox' --glob '*.py'`
>
> - Wrote `./myboerse_scraper.py` (+4 -6)
> - Wrote `./readme.md` (+2 -2)
> - Wrote `./requirements.txt` (+1 -1)
> - Wrote `./shell.nix` (+0 -7)
>
> - Ran `git diff --check && python3 myboerse_scraper.py --help && git status --short`
>
> - Ran `nix-instantiate --parse shell.nix >/dev/null && python3 -m camoufox path`
>
> <details><summary>Explored a file, a list</summary>
>
> - Read `./myboerse_scraper.py`
> - Listed files in `camoufox`
>
> </details>
>
> </details>
>
> The browser startup and setup files now use Camoufox. The CLI and Nix syntax checks passed, and I’ll test browser startup with an offline forum fixture.
>
> <details><summary>Ran 5 commands</summary>
>
> - Ran `timeout 25s python3 - <<'PY'
> import asyncio
> import json
> import os
> import tempfile
> from pathlib import Path
> from types import SimpleNamespace
> import myboerse_scraper as scraper
>
> original = scraper.AsyncCamoufox
> thread = "<html><body>" + "archived content " * 100 + "</body></html>"
> pages = {
>     "/": '<a href="/logout">Account</a>',
>     "/members/test.1/": '<a href="/search/member?content=thread">Threads</a>',
>     "/search/member?content=thread": '<ol class="block-body"><li class="block-row"><div class="contentRow"><div class="contentRow-main"><h3 class="contentRow-title"><a href="/threads/sample.42/">Sample</a></h3></div></div></li></ol>',
>     "/threads/sample.42/": thread,
> }
>
> class FixtureBrowser(original):
>     async def __aenter__(self):
>         browser = await super().__aenter__()
>         async def route_fixture(route):
>             key = route.request.url.removeprefix("https://myboerse.bz")
>             if key in pages:
>                 await route.fulfill(content_type="text/html", body=pages[key])
>             else:
>                 await route.abort()
>         class Browser:
>             async def new_context(self, **options):
>                 context = await browser.new_context(**options)
>                 await context.route("**/*", route_fixture)
>                 return context
>         return Browser()
>
> async def run():
>     scraper.AsyncCamoufox = FixtureBrowser
>     with tempfile.TemporaryDirectory() as tmp:
>         os.chdir(tmp)
>         Path("config.json").write_text(json.dumps({}))
>         args = SimpleNamespace(config="config.json", start_url="https://myboerse.bz/members/test.1/",
>                                output="archive", headless=True, delay=0)
>         assert await scraper.async_main(args) == 0
>         assert "archived content" in Path("archive/42.html").read_text()
>
> asyncio.run(run())
> PY`
> - Ran `PYTHONUNBUFFERED=1 timeout 15s python3 - <<'PY'
> import asyncio
> from camoufox.async_api import AsyncCamoufox
> async def run():
>     async with AsyncCamoufox(headless=True, timeout=10000) as browser:
>         print("launched")
>         context = await browser.new_context(accept_downloads=False, locale="de-DE", user_agent=None)
>         page = await context.new_page()
>         await page.goto("data:text/html,<title>Smoke test</title>")
>         assert await page.title() == "Smoke test"
>         await context.close()
>         print("passed")
> asyncio.run(run())
> PY`
> - Ran `python3 -m camoufox --help && ls -la /home/user/.cache/camoufox && printenv | sort | cut -d= -f1 | rg 'CAMOUFOX|FIREFOX|PLAYWRIGHT'`
> - Ran `DEBUG=pw:browser PYTHONUNBUFFERED=1 timeout 12s python3 - <<'PY'
> import asyncio
> from camoufox.async_api import AsyncCamoufox
> async def main():
>     async with AsyncCamoufox(headless=True, timeout=5000) as browser:
>         page = await browser.new_page(accept_downloads=False, locale="de-DE")
>         await page.goto("data:text/html,<title>Smoke test</title>")
>         assert await page.title() == "Smoke test"
>         print("passed")
> asyncio.run(main())
> PY`
> - Ran `PYTHONUNBUFFERED=1 timeout 30s python3 - <<'PY'
> import asyncio
> from camoufox.async_api import AsyncCamoufox
> async def main():
>     async with AsyncCamoufox(headless=True) as browser:
>         context = await browser.new_context(accept_downloads=False, locale="de-DE", user_agent=None)
>         page = await context.new_page()
>         await page.goto("data:text/html,<title>Smoke test</title>")
>         assert await page.title() == "Smoke test"
>         await context.close()
>     print("Camoufox browser smoke test passed")
> asyncio.run(main())
> PY`
>
> </details>
</details>

Migrated the MyBoerse scraper from Patchright to Camoufox. The existing CLI, login flow, and HTML archiving behavior are preserved. Updated the Python dependencies, Nix shell, and setup instructions.

The CLI and Nix syntax checks passed, and Camoufox successfully opened a page in headless mode. Live forum login and scraping remain unverified.

For a pip-based setup, install the updated requirements and fetch the browser with `python -m camoufox fetch`.
