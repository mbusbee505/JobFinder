# evaluate_multiuser.py - Multi-user evaluation wrapper

from evaluate import analyze_job
from typing import Dict, Any, Optional


def analyze_job_for_user(job_description: str, user_id: int, resume: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyze a job posting for a specific user using their configuration.
    This is a wrapper around evaluate.analyze_job for clarity in multiuser context.
    """
    return analyze_job(job_description=job_description, user_id=user_id, resume=resume)
