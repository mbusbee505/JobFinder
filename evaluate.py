# evaluate.py
import re
try:
    # Try to import from multi-user utils first
    from utils_multiuser import load_user_config as get_user_config
except ImportError:
    # Fall back to single-user config
    from config import get_user_config

import os
import json
from typing import List, Dict, Any, Callable, Optional

import openai
import google.generativeai as genai
from google.generativeai import types as gen_types

# Global configs will be loaded per-user

#_OPENAI_MODEL = "gpt-4.1-mini"  # OpenAI model identifier
_OPENAI_MODEL = "o3"  # OpenAI model identifier
_GEMINI_MODEL = "models/gemini-2.5-flash-preview-04-17"

_FENCE_RE = re.compile(r"^```(?:json)?\n|\n```$", re.S)



def contains_exclusions(title, exclusion_keywords=None):
    """Check if title contains exclusion keywords.
    If exclusion_keywords is not provided, this will be empty (backwards compatibility)
    """
    if not exclusion_keywords:
        return False
    return any(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", title, re.I)
               for word in exclusion_keywords)

def sanitize_text(text: str) -> str:
    """
    Remove or replace non-ASCII characters.
    Replaces common Unicode punctuation with ASCII equivalents.
    """
    # Dictionary of Unicode to ASCII replacements
    replacements = {
        '\u2011': '-',  # Non-breaking hyphen
        '\u2013': '-',  # En dash
        '\u2014': '-',  # Em dash
        '\u2018': "'",  # Left single quote
        '\u2019': "'",  # Right single quote
        '\u201c': '"',  # Left double quote
        '\u201d': '"',  # Right double quote
    }

    # Replace known Unicode characters
    for unicode_char, ascii_char in replacements.items():
        text = text.replace(unicode_char, ascii_char)

    # Remove any remaining non-ASCII characters
    return ''.join(char for char in text if ord(char) < 128)

def prompt_eligibility(job_description: str, user_config: dict, resume: Optional[str] = None) -> str:
    base = (
        "You are an AI recruiter assistant.\n"
        "You are a helpful assistant that evaluates job postings with a realistic understanding of hiring practices. "
        "Remember that many job 'requirements' are actually preferences, and hiring managers often consider candidates who meet 70-80% of listed requirements. "
        "Analyse the following LinkedIn job description and determine whether the "
        "candidate is eligible for the role."
        "Assume the candidate is eligible via US citizenship or residency requirements."
    )

    # Add evaluation criteria from user config
    prompts_config = user_config.get('prompts', {})
    if 'evaluation_prompt' in prompts_config:
        base += f"\n\nEvaluation Criteria:\n{prompts_config['evaluation_prompt']}"

    # Use user's resume if provided, fallback to user config resume
    if not resume:
        resume = user_config.get('resume', {}).get('text')

    if resume:
        base += f"\n\nJob Description:\n{sanitize_text(job_description.strip())}\n\nCandidate Resume:\n{sanitize_text(resume.strip())}"
    else:
        base += f"\n\nJob Description:\n{sanitize_text(job_description.strip())}"
    base += (
        "\n\nRespond using ONLY valid JSON with the following schema:\n"
        "{\n"
        "  \"eligible\": bool,\n"
        "  \"reasoning\": str,\n"
        "  \"missing_requirements\": [str]\n"
        "}"
    )
    return base

def call_openai(prompt: str, api_key: str) -> Dict[str, Any]:
    import httpx

    # Ensure the prompt is ASCII-only
    sanitized_prompt = sanitize_text(prompt)

    # Create a custom httpx client without proxy support to avoid the 'proxies' error
    http_client = httpx.Client(
        timeout=60.0,
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
    )

    # Create OpenAI client with custom HTTP client
    client = openai.OpenAI(
        api_key=api_key,
        http_client=http_client
    )

    response = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[{"role": "user", "content": sanitized_prompt}],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)

def call_gemini(prompt: str, user_config: dict) -> dict:
    google_api_key = user_config.get("api_keys", {}).get("google_api_key")

    if not google_api_key or google_api_key == "YOUR_GOOGLE_API_KEY_HERE":
        raise ValueError("Google API Key not configured for user or is a placeholder.")

    # Configure Gemini API key before making a call
    # This configuration is sticky for the genai module until changed again or process ends.
    try:
        genai.configure(api_key=google_api_key)
    except Exception as e:
        # genai.configure can raise if api_key is invalid format, etc.
        raise ValueError(f"Failed to configure Google Gemini API: {e}")

    model = genai.GenerativeModel(_GEMINI_MODEL)
    resp = model.generate_content(
        prompt,
    )
    txt = _FENCE_RE.sub("", resp.text.strip())
    return json.loads(txt)


def analyze_job(
    job_description: str,
    user_id: int,
    resume: Optional[str] = None,
) -> Dict[str, Any]:

    # Get user-specific configuration
    user_config = get_user_config(user_id)
    prompt = prompt_eligibility(job_description, user_config, resume)

    provider_to_use = user_config.get("general", {}).get("ai_provider", "openai").lower()

    if provider_to_use == "openai":
        # Get OpenAI API key
        openai_api_key = user_config.get("api_keys", {}).get("openai_api_key")
        if not openai_api_key or openai_api_key == "YOUR_OPENAI_API_KEY_HERE":
            raise ValueError(f"OpenAI API Key not configured for user {user_id} or is a placeholder.")

        # Return the OpenAI response directly
        return call_openai(prompt, openai_api_key)
    elif provider_to_use == "gemini":
        # Gemini configuration is handled within call_gemini itself to ensure it happens just before model instantiation
        return call_gemini(prompt, user_config)
    else:
        raise ValueError(f"Invalid AI provider configured for user {user_id}: '{provider_to_use}'. Must be 'openai' or 'gemini'.")


def batch_analyse_jobs(
    job_descriptions: List[str],
    user_id: int,
    resume: Optional[str] = None,
    temperature: float = 0,
) -> List[Dict[str, Any]]:
    return [
        analyze_job(desc, user_id, resume=resume)
        for desc in job_descriptions
    ]