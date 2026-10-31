# MyBoerse thread archiver

Archives thread pages as HTML using Patchright. The current implementation supports member profile URLs only.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
python -m pip install -r requirements.txt
patchright install chromium
```

Create a private JSON config, for example `config.json`:

```json
{
  "username": "YOUR_FORUM_USERNAME",
  "password": "YOUR_FORUM_PASSWORD"
}
```

Keep this file private and do not commit it to version control. Restrict its filesystem permissions where possible.

## Run

```bash
python myboerse_scraper.py \
  --config config.json \
  --start-url "https://myboerse.bz/members/thewooter.124199/" \
  --output "./archive/thewooter"
```

The browser is visible by default, which helps if the forum presents a challenge or additional login step. Use `--headless` only after confirming that login works in your environment.

## Cache behavior

Files are named `<thread-id>.html`. Existing files are never refreshed or overwritten; delete a file manually if you want to download that thread again. New files are written atomically so an interrupted download won't leave a partial file that gets mistaken for a completed archive.

## Scope and notes

- The script follows the member page's own "find all threads" link, then follows XenForo search pagination.
- It saves each thread page's HTML. Filecrypt links remain as links in that HTML; the script does not visit or download from Filecrypt.
- Non-member start URLs intentionally raise `NotImplementedError` until a handler is implemented.
- Forum markup and login behavior can change. If it reports no thread results, inspect the visible browser and update the XenForo selectors in `extract_thread_links()` / `find_next_page()`.
- Use only for content you are authorized to access, and keep request rates modest.
