# MyBoerse and MyGully thread archiver

Archives thread pages as HTML using Camoufox. Use a MyBoerse member profile URL or a MyGully subforum URL.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m camoufox fetch
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

For MyGully, use your MyGully credentials in the config and pass the subforum URL with any filters you want to keep across listing pages.

```bash
python myboerse_scraper.py \
  --config mygully-config.json \
  --start-url 'https://mygully.com/forum/104-ha-rba-cher-und-ha-rspiele/?pp=50&daysprune=-1&prefixid=SachbuchEbooks'
```

MyGully archives default to `archive/mygully.com/<thread-id>.html`. MyBoerse archives default to `archive/myboerse/<thread-id>.html`.

The browser is visible by default, which helps if the forum presents a challenge or additional login step. Use `--headless` only after confirming that login works in your environment.

## Cache behavior

Files are named `<thread-id>.html`. Existing files are never refreshed or overwritten; delete a file manually if you want to download that thread again. New files are written atomically so an interrupted download won't leave a partial file that gets mistaken for a completed archive.

## Scope and notes

- For MyBoerse, the script follows the member page's "find all threads" link and then XenForo search pagination.
- For MyGully, the script follows the subforum's pagination and keeps the filters from the start URL.
- Filehoster links remain in the archived HTML. The script opens only the forum listing and thread pages during scraping.
- Use only for content you are authorized to access, and keep request rates modest.

## Limitations

### Rate-limiting

On too many requests, filecrypt.cc starts returning a fake HTTP 404 (Not Found) response status code,
when it actually should return an HTTP 429 (Too Many Requests) response status code.
This happens after about 70 to 100 consecutive requests.
The block lasts for maximum 24 hours, probably less.
