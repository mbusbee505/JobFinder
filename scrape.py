# scrape.py

import requests
from bs4 import BeautifulSoup
import evaluate
from evaluate import analyze_job
import json, html, re, urllib
from urllib.parse import urlparse, parse_qs
from config import load, get_user_config
import database
import random
from typing import Sequence, List, TypeVar, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from http import HTTPStatus
import sys

T = TypeVar("T")

# Config will be loaded per-user in functions below

MAX_WORKERS = 5
RETRIES     = 4
BASE_DELAY  = 2  # seconds

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


_JOB_ID_RE = re.compile(r"/jobs/view/(?:[^/?]*-)?(\d+)(?:[/?]|$)")

def shuffled(seq: Sequence[T]) -> List[T]:
    """Return a new list containing all items from *seq* in random order."""
    tmp = list(seq)          # copy so the caller's list is untouched
    random.shuffle(tmp)
    return tmp

def process_search_page(search, stop_signal=None) -> int:
    handled = 0
    jobs_for_update = []

    # Check for stop signal before starting
    if stop_signal and stop_signal[0]:
        return 0

    soup = get_soup(search["url"])
    if soup is None:
        return 0

    for a in soup.find_all("a", href=True):
        # Check for stop signal periodically
        if stop_signal and stop_signal[0]:
            print(f"  Stop signal detected during link processing. Handled {handled} links so far.")
            sys.stdout.flush()
            break

        if "/jobs/view/" not in a["href"]:
            continue
        handled += 1

        full   = "https://www.linkedin.com" + a["href"] if a["href"].startswith("/") else a["href"]
        url    = canonical_job_url(full)
        job_id = extract_job_id(url)
        if job_id is None:
            continue

        is_new = database.insert_stub(job_id, url, search["location"], search["keyword"])
        if is_new or database.row_missing_details(job_id):
            jobs_for_update.append({"job_id": job_id, "url": url})

    # Process jobs with stop signal monitoring
    if jobs_for_update and not (stop_signal and stop_signal[0]):
        # Use a custom function that can check stop signals
        _process_jobs_with_stop_check(jobs_for_update, stop_signal)

    return handled

def _process_jobs_with_stop_check(jobs_for_update, stop_signal=None):
    """Process jobs with periodic stop signal checking"""
    processed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        # Submit jobs in smaller batches to allow stop checking
        batch_size = min(5, len(jobs_for_update))
        for i in range(0, len(jobs_for_update), batch_size):
            # Check stop signal before each batch
            if stop_signal and stop_signal[0]:
                print(f"  Stop signal detected. Processed {processed}/{len(jobs_for_update)} jobs.")
                sys.stdout.flush()
                break

            batch = jobs_for_update[i:i + batch_size]
            # Add stop_signal to each job for checking
            batch_with_signal = [{"stop_signal": stop_signal, **job} for job in batch]

            futures = [pool.submit(_fetch_and_update_with_stop, job_data) for job_data in batch_with_signal]

            # Wait for batch completion with stop checking
            for future in futures:
                if stop_signal and stop_signal[0]:
                    break
                try:
                    future.result(timeout=30)  # 30 second timeout per job
                    processed += 1
                except Exception as e:
                    print(f"  Error processing job: {e}")
                    processed += 1

def get_searches(user_id):
    """Get search parameters for a specific user."""
    searches = []

    # Get user-specific configuration
    user_config = get_user_config(user_id)
    search_params = user_config.get("search_parameters", {})
    locations = search_params.get("locations", [])
    keywords = search_params.get("keywords", [])

    if not locations or not keywords:
        print(f"Warning: User {user_id} has no search parameters configured")
        return searches

    for location in shuffled(locations):
        for keyword in shuffled(keywords):

            if location.lower() == "remote":
                # Search for remote positions
                url = f"https://www.linkedin.com/jobs/search/?keywords={keyword.replace(' ', '%20')}&f_WT=2"
                searches.append({"url": url, "location": location, "keyword": keyword})
            else:
                url = f"https://www.linkedin.com/jobs/search/?keywords={keyword.replace(' ', '%20')}&location={location.replace(' ', '%20')}&distance=75&f_WT=1"
                searches.append({"url": url, "location": location, "keyword": keyword})
                url = f"https://www.linkedin.com/jobs/search/?keywords={keyword.replace(' ', '%20')}&location={location.replace(' ', '%20')}&distance=75&f_WT=3"
                searches.append({"url": url, "location": location, "keyword": keyword})

    return searches

def get_soup(url):
    HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
    }
    soup = None
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        soup =  BeautifulSoup(resp.text, 'html.parser')
    return soup

def extract_job_urls(soups, user_id=None):
    if soups is None:
        return []
    if hasattr(soups, "find_all"):
        soups = [soups]

    # Get exclusion keywords for the user
    if user_id:
        user_config = get_user_config(user_id)
        exclusion_keywords = user_config.get("search_parameters", {}).get("exclusion_keywords", [])
    else:
        exclusion_keywords = []

    job_urls = set()
    for soup in soups:
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            if evaluate.contains_exclusions(text, exclusion_keywords):
                continue
            href = a["href"]
            if "/jobs/view/" not in href:
                continue

            href = "https://www.linkedin.com" + href if href.startswith("/") else href
            canon = canonical_job_url(href)
            job_urls.add(canon if canon else href)


    return list(job_urls)

def strip_html_tags(raw: str) -> str:
    return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)

def clean_description(raw_html: str) -> str:

    # First, decode HTML entities
    decoded = html.unescape(raw_html)

    # Remove nested tags, keeping their text content
    def strip_tags(text):
        return re.sub('<[^<]+?>', '', text)

    # Remove all HTML tags
    no_tags = strip_tags(decoded)

    # Replace multiple newlines/spaces with single space
    cleaned = re.sub(r'\s+', ' ', no_tags)

    # Optional: Convert list-like structures to more readable format
    cleaned = re.sub(r'\s*•\s*', '\n• ', cleaned)
    cleaned = re.sub(r'\s*-\s*', '\n- ', cleaned)

    # Remove common LinkedIn boilerplate
    boilerplate_patterns = [
        r'Pay Range:.*',
        r'The specific compensation.*',
        r'Full job description.*',
        r'About the job.*'
    ]
    for pattern in boilerplate_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    return cleaned.strip()

def canonical_job_url(raw: str) -> Optional[str]:
    """
    Return 'https://www.linkedin.com/jobs/view/<id>/' for any flavour of
    LinkedIn job link.  Handles:

      • /jobs/view/4191603147
      • /jobs/view/security-operations-center-...-4191603147
      • /jobs/view/?currentJobId=4191603147
    """
    parsed = urlparse(raw)

    # 1) ID lives somewhere in the path (the common case)
    m = _JOB_ID_RE.search(parsed.path)
    if m:
        job_id = m.group(1)
        return f"https://www.linkedin.com/jobs/view/{job_id}/"

    # 2) ID only appears in the query string (rare but possible)
    qs = parse_qs(parsed.query)
    for key in ("currentJobId", "jobId"):
        if key in qs and qs[key]:
            return f"https://www.linkedin.com/jobs/view/{qs[key][0]}/"

    return None        # caller can fall back to the raw href if desired

def extract_job_description(job_soup):
    # 1) look for ld+json
    for script in job_soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
        except Exception:
            continue
        if isinstance(data, dict) and "description" in data:
            return clean_description(data["description"])

    # 2) fallback to decoratedJobPosting = {...};
    pattern = re.compile(r"decoratedJobPosting\":({.*?})},\"applyMethod",
                         re.DOTALL)
    m = pattern.search(job_soup.text)
    if m:
        data = json.loads(m.group(1))
        if "description" in data:
            return clean_description(data["description"])

    # 3) last-chance: try the old div selectors (for logged-in HTML)
    container = job_soup.find(id="job-details") or \
                job_soup.find("div",
                    class_=lambda c: c and "jobs-description__content" in c)
    if container:
        return clean_description(container.decode_contents())

    return None

def extract_job_title(job_soup):
    """Try several possible selectors / patterns to obtain the job title text from a LinkedIn job page."""
    # common places the title shows up on a full job page
    title_selectors = [
        ('h1', {'class_': 'topcard__title'}),
        ('h1', {'class_': 'jobs-unified-top-card__job-title'}),
        ('h1', {'class_': 'jobs-details-top-card__job-title'}),
        ('h1', {}),                       # plain first H1
        ('h2', {'class_': 'topcard__title'}),
        ('h2', {'class_': 't-24'}),       # generic large heading
        ('div', {'class_': 'job-title'}),
        ('span', {'class_': 'job-title'}),
    ]

    for tag, attrs in title_selectors:
        element = job_soup.find(tag, attrs)
        if element:
            title = element.get_text(strip=True)
            if title:
                return title

    # Fallback: meta og:title – often contains e.g. "Job Title – Company | LinkedIn"
    og_title = job_soup.find('meta', property='og:title')
    if og_title and og_title.get('content'):
        return og_title['content'].split('|')[0].strip()

    return None

def extract_job_id(url: str) -> Optional[int]:
    m = _JOB_ID_RE.search(urllib.parse.urlparse(url).path)
    if m:
        return int(m.group(1))
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    for key in ("currentJobId", "jobId"):
        if key in qs and qs[key]:
            return int(qs[key][0])
    return None

def get_jobs():
    searches = get_searches()
    jobs = []
    for search  in searches:
        url = search["url"]
        location = search["location"]
        keyword = search["keyword"]
        soup = get_soup(url)
        job_urls = extract_job_urls(soup)
        for url in job_urls:
            jobs.append({"url": url, "location": location, "keyword": keyword})
        #job_urls.extend(extract_job_urls(soup))


    seen = set()
    unique_jobs = []

    for job in jobs:
        if job["url"] not in seen:
            seen.add(job["url"])
            unique_jobs.append(job)
    return unique_jobs

def get_job_data(job):
    url = job["url"]
    location = job["location"]
    keyword = job["keyword"]
    job_soup = get_soup(url)
    title = ""
    description = ""

    job_data = {
        "url": url,
        "location": location,
        "keyword": keyword,
        "title": title,
        "description": description,
    }

    return job_data

def _fetch_and_update_with_stop(job_data: dict) -> None:
    """Wrapper for _fetch_and_update that checks stop signals"""
    stop_signal = job_data.get("stop_signal")
    if stop_signal and stop_signal[0]:
        return

    # Remove stop_signal from job data before processing
    job = {k: v for k, v in job_data.items() if k != "stop_signal"}
    _fetch_and_update(job, stop_signal)

def _fetch_and_update(job: dict, stop_signal=None) -> None:
    # For timing, uncomment if desired
    # start_time_total = time.time()

    title = None # Initialize to None
    desc = None  # Initialize to None
    linkedin_job_id = job["job_id"]
    job_url = job["url"]

    # Get user config for exclusion keywords
    user_config = get_user_config(database.ADMIN_USER_ID)
    exclusion_keywords = user_config.get("search_parameters", {}).get("exclusion_keywords", [])

    soup = get_soup(job_url) # Use job_url consistently
    if soup:
        title = extract_job_title(soup)
        desc  = extract_job_description(soup)

    # Check stop signal before exclusion check
    if stop_signal and stop_signal[0]:
        return

    # ADDED BLOCK: Check exclusions against the full title
    if title and evaluate.contains_exclusions(title, exclusion_keywords):
        # sys.stdout.write(f"INFO: Job ID {linkedin_job_id} ('{title}') excluded based on full title.\\n") # Optional logging
        # sys.stdout.flush()
        database.mark_job_as_analyzed(job_id=linkedin_job_id) # Mark as analyzed to prevent re-processing
        return # Skip further processing for this job

    # Check stop signal before guest fetch
    if stop_signal and stop_signal[0]:
        return

    if title is None or desc is None:
        g_title, g_desc = _fetch_guest(linkedin_job_id)
        if title is None:
            title = g_title
        if desc is None:
            desc = g_desc

    # ADDED: Second exclusion check for title obtained from fallback
    if title and evaluate.contains_exclusions(title, exclusion_keywords):
        database.mark_job_as_analyzed(job_id=linkedin_job_id)
        return

    # Check stop signal before database update
    if stop_signal and stop_signal[0]:
        return

    if title is not None or desc is not None:
        database.update_details(linkedin_job_id, title, desc)

    # Check stop signal before expensive AI analysis
    if stop_signal and stop_signal[0]:
        return

    if desc and desc.strip():
        try:
            # For timing, uncomment if desired
            # ai_eval_start_time = time.time()

            ai_response = analyze_job(job_description=desc, user_id=database.ADMIN_USER_ID)

            # For timing, uncomment if desired
            # print(f"Job ID {linkedin_job_id}: AI analysis took {time.time() - ai_eval_start_time:.2f}s")

            if ai_response.get("eligible"):
                reasoning = ai_response.get("reasoning", "No reasoning provided by AI.")

                # Call approve_job once and store its result
                was_newly_approved = database.approve_job(linkedin_job_id=linkedin_job_id, reason=reasoning)

                if was_newly_approved:
                    # Print details to console only if it was newly approved
                    output_message = (
                        f"\n[APPROVED] Job ID: {linkedin_job_id}\n"
                        f"  Title: {title if title else 'N/A - Title not found'}\n"
                        f"  URL: {job_url}\n"
                        f"  Reason: {reasoning}\n"
                    )
                    sys.stdout.write(output_message)
                    sys.stdout.flush()
        except Exception as e:
            error_message = f"\nError during AI analysis or approval for job_id {linkedin_job_id}: {e}\n"
            sys.stdout.write(error_message)
            sys.stdout.flush()

    database.mark_job_as_analyzed(job_id=linkedin_job_id)
    # For timing, uncomment if desired
    # print(f"Job ID {linkedin_job_id}: Total _fetch_and_update took {time.time() - start_time_total:.2f}s")



def _safe_fetch(url: str) -> Optional[str]:
    delay = BASE_DELAY
    for _ in range(RETRIES):
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.text
        if r.status_code in (429, 502, 503, 504):
            time.sleep(delay)
            delay *= 2
            continue
        return None
    return None


def _fetch_guest(job_id: int) -> tuple[Optional[str], Optional[str]]:
    url  = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    html = _safe_fetch(url)
    if not html:
        return None, None
    soup = BeautifulSoup(html, "html.parser")

    t_el = soup.find("h2", class_="top-card-layout__title")
    d_el = soup.find("div", class_="description__text") or \
           soup.find("section", class_="show-more-less-html")

    title = t_el.get_text(strip=True) if t_el else None
    desc  = clean_description(d_el.decode_contents()) if d_el else None
    return title, desc

def _rowcount(user_id) -> int:
    """Returns the current count of discovered_jobs for a user."""
    return database.get_user_job_count(user_id)

def show_progress(idx: int, total: int, bar_len: int = 40) -> None:
    """Render a simple progress bar like  [██████------] 12/44 (27%)"""
    # This function uses sys, ensure 'sys' module is imported in scrape.py
    pct   = idx / total if total > 0 else 0 # Avoid division by zero
    filled = int(bar_len * pct)
    bar   = "█" * filled + "-" * (bar_len - filled)
    # Use sys.stdout.write for progress bar to allow overwriting
    sys.stdout.write(f"\r[{bar}] {idx}/{total} ({pct:.0%})")
    sys.stdout.flush()

def scrape_phase(stop_signal: List[bool]) -> tuple[int, int]:
    """
    Conducts the scraping phase.
    Returns a tuple: (new_jobs_this_run, total_links_examined)
    """
    # This function uses _rowcount, get_searches, process_search_page, show_progress
    # Ensure 'database' module is imported for _rowcount.
    # Ensure 'sys' is imported for show_progress and print flushing.
    print("Initializing scraping: Generating search list...")
    sys.stdout.flush()

    # ADDED: Load/Reload config before generating searches
    try:
        config = load() # Reload config from file
        # Update local variables if needed based on reloaded config
        locations = config.get("search_parameters", {}).get("locations", [])
        keywords = config.get("search_parameters", {}).get("keywords", [])
    except Exception as e:
        print(f"WARN: Failed to reload config before scraping: {e}. Using potentially stale config.")
        # Optionally handle error more gracefully, e.g., stop if config is crucial and failed to load

    start_total_db_rows = _rowcount(database.ADMIN_USER_ID)
    searches = get_searches(database.ADMIN_USER_ID) # Assumes get_searches is defined in scrape.py
    total_searches = len(searches)

    if not searches:
        print("No search criteria defined in config.toml or an issue occurred generating searches.")
        return 0, 0 # No new jobs, no links examined

    print(f"Generated {total_searches} search permutations. Starting job processing...")
    sys.stdout.flush()

    total_links_examined_this_run = 0
    try:
        for i, search in enumerate(searches, 1):
            # Check both the immediate signal and the persistent DB signal
            if (stop_signal and stop_signal[0]) or database.should_stop_scan(): # MODIFIED
                sys.stdout.write("\nINFO: Scrape phase received stop signal. Terminating early.\n")
                sys.stdout.flush()
                database.set_stop_scan_flag(False) # Reset the flag after acknowledging stop
                break

            links_on_page = process_search_page(search, stop_signal) or 0 # process_search_page is in scrape.py
            total_links_examined_this_run += links_on_page
            show_progress(i, total_searches)
    except KeyboardInterrupt:
        sys.stdout.write("\n⚠️  Interrupted by user during scraping – finishing up current operations…\n")
        sys.stdout.flush()
    finally:
        # Ensure a newline after the progress bar finishes or is interrupted
        sys.stdout.write("\n")
        sys.stdout.flush()

        end_total_db_rows = _rowcount(database.ADMIN_USER_ID)
        new_jobs_this_run = end_total_db_rows - start_total_db_rows

        print("──────────────── Scrape Phase Summary ────────────────")
        print(f"Links examined this run: {total_links_examined_this_run}")
        print(f"New jobs added to DB this run: {new_jobs_this_run}")
        print(f"Total discovered jobs in database: {end_total_db_rows}")
        print("──────────────────────────────────────────────────")
        sys.stdout.flush()
        return new_jobs_this_run, total_links_examined_this_run

if __name__ == "__main__":
    searches = get_searches()
    total_links, kept, dropped = 0, 0, 0

    for s in searches:
        soup = get_soup(s["url"])
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/jobs/view/" not in href:
                continue
            total_links += 1
            canon = canonical_job_url("https://www.linkedin.com" + href if href.startswith("/") else href)
            if canon is None:
                dropped += 1
                print("❌  DID NOT MATCH:", href[:120])
            else:
                kept += 1
    print(f"\n{total_links=}  {kept=}  {dropped=}")