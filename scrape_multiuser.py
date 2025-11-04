# scrape_multiuser.py - Multi-user scraping wrapper

import sys
from typing import List
import database_multiuser as database
from scrape import (
    get_searches,
    show_progress,
    get_soup,
    canonical_job_url,
    extract_job_id,
    extract_job_description,
    extract_job_title,
    _fetch_guest,
    clean_description
)
from evaluate_multiuser import analyze_job_for_user


def scrape_phase_for_user(user_id: int, stop_signal: List[bool]) -> tuple[int, int]:
    """
    Conducts the scraping phase for a specific user.
    Returns a tuple: (new_jobs_this_run, total_links_examined)
    """
    print(f"[User {user_id}] Initializing scraping: Generating search list...")
    sys.stdout.flush()

    # Get initial database row count
    start_total_db_rows = database.get_user_job_count(user_id)

    # Get search parameters for this user
    searches = get_searches(user_id)
    total_searches = len(searches)

    if not searches:
        print(f"[User {user_id}] No search criteria defined in config.")
        return 0, 0

    print(f"[User {user_id}] Generated {total_searches} search permutations. Starting job processing...")
    sys.stdout.flush()

    total_links_examined_this_run = 0

    try:
        for i, search in enumerate(searches, 1):
            # Check both the immediate signal and the persistent DB signal
            if (stop_signal and stop_signal[0]) or database.should_stop_scan(user_id):
                sys.stdout.write(f"\n[User {user_id}] INFO: Scrape phase received stop signal. Terminating early.\n")
                sys.stdout.flush()
                database.set_stop_scan_flag(user_id, False)  # Reset the flag after acknowledging stop
                break

            links_on_page = process_search_page_for_user(search, user_id, stop_signal) or 0
            total_links_examined_this_run += links_on_page
            show_progress(i, total_searches)

    except KeyboardInterrupt:
        sys.stdout.write(f"\n[User {user_id}] ⚠️  Interrupted by user during scraping – finishing up current operations…\n")
        sys.stdout.flush()
    finally:
        # Ensure a newline after the progress bar finishes or is interrupted
        sys.stdout.write("\n")
        sys.stdout.flush()

        end_total_db_rows = database.get_user_job_count(user_id)
        new_jobs_this_run = end_total_db_rows - start_total_db_rows

        print(f"[User {user_id}] ──────────────── Scrape Phase Summary ────────────────")
        print(f"[User {user_id}] Links examined this run: {total_links_examined_this_run}")
        print(f"[User {user_id}] New jobs added to DB this run: {new_jobs_this_run}")
        print(f"[User {user_id}] Total discovered jobs in database: {end_total_db_rows}")
        print(f"[User {user_id}] ──────────────────────────────────────────────────")
        sys.stdout.flush()

        return new_jobs_this_run, total_links_examined_this_run


def process_search_page_for_user(search, user_id: int, stop_signal=None) -> int:
    """Process a search page for a specific user"""
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
            print(f"  [User {user_id}] Stop signal detected during link processing. Handled {handled} links so far.")
            sys.stdout.flush()
            break

        if "/jobs/view/" not in a["href"]:
            continue
        handled += 1

        full = "https://www.linkedin.com" + a["href"] if a["href"].startswith("/") else a["href"]
        url = canonical_job_url(full)
        job_id = extract_job_id(url)
        if job_id is None:
            continue

        is_new = database.insert_stub(user_id, job_id, url, search["location"], search["keyword"])
        if is_new or database.row_missing_details(user_id, job_id):
            jobs_for_update.append({"job_id": job_id, "url": url, "user_id": user_id})

    # Process jobs with stop signal monitoring
    if jobs_for_update and not (stop_signal and stop_signal[0]):
        _process_jobs_for_user(jobs_for_update, user_id, stop_signal)

    return handled


def _process_jobs_for_user(jobs_for_update, user_id: int, stop_signal=None):
    """Process jobs for a specific user sequentially"""
    processed = 0
    total = len(jobs_for_update)

    for job_data in jobs_for_update:
        # Check stop signal before each job
        if stop_signal and stop_signal[0]:
            print(f"  [User {user_id}] Stop signal detected. Processed {processed}/{total} jobs.")
            sys.stdout.flush()
            break

        try:
            _fetch_and_update_for_user(job_data, user_id, stop_signal)
            processed += 1
        except Exception as e:
            print(f"  [User {user_id}] Error processing job {job_data.get('job_id')}: {e}")
            processed += 1


def _fetch_and_update_for_user(job: dict, user_id: int, stop_signal=None) -> None:
    """Fetch and update job details for a specific user"""
    title = None
    desc = None
    linkedin_job_id = job["job_id"]
    job_url = job["url"]

    # Get user config for exclusion keywords
    from utils_multiuser import load_user_config
    user_config = load_user_config(user_id)
    exclusion_keywords = user_config.get("search_parameters", {}).get("exclusion_keywords", [])

    soup = get_soup(job_url)
    if soup:
        title = extract_job_title(soup)
        desc = extract_job_description(soup)

    # Check stop signal
    if stop_signal and stop_signal[0]:
        return

    # Check exclusions against the title
    from evaluate import contains_exclusions
    if title and contains_exclusions(title, exclusion_keywords):
        database.mark_job_as_analyzed(user_id, linkedin_job_id)
        return

    # Check stop signal before guest fetch
    if stop_signal and stop_signal[0]:
        return

    # Fallback to guest API if needed
    if title is None or desc is None:
        g_title, g_desc = _fetch_guest(linkedin_job_id)
        if title is None:
            title = g_title
        if desc is None:
            desc = g_desc

    # Second exclusion check for title obtained from fallback
    if title and contains_exclusions(title, exclusion_keywords):
        database.mark_job_as_analyzed(user_id, linkedin_job_id)
        return

    # Check stop signal before database update
    if stop_signal and stop_signal[0]:
        return

    # Update job details in database
    if title is not None or desc is not None:
        database.update_details(user_id, linkedin_job_id, title, desc)

    # Check stop signal before expensive AI analysis
    if stop_signal and stop_signal[0]:
        return

    # Perform AI analysis if we have a description
    if desc and desc.strip():
        try:
            ai_response = analyze_job_for_user(job_description=desc, user_id=user_id)

            if ai_response.get("eligible"):
                reasoning = ai_response.get("reasoning", "No reasoning provided by AI.")

                # Approve the job for this user
                was_newly_approved = database.approve_job(user_id, linkedin_job_id, reason=reasoning)

                if was_newly_approved:
                    # Print details to console only if it was newly approved
                    output_message = (
                        f"\n[User {user_id}] [APPROVED] Job ID: {linkedin_job_id}\n"
                        f"  Title: {title if title else 'N/A - Title not found'}\n"
                        f"  URL: {job_url}\n"
                        f"  Reason: {reasoning}\n"
                    )
                    sys.stdout.write(output_message)
                    sys.stdout.flush()
        except Exception as e:
            error_message = f"\n[User {user_id}] Error during AI analysis or approval for job_id {linkedin_job_id}: {e}\n"
            sys.stdout.write(error_message)
            sys.stdout.flush()

    # Mark job as analyzed
    database.mark_job_as_analyzed(user_id, linkedin_job_id)
