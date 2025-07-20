// Dashboard-specific JavaScript for JobFinder

// Resume generation function
function generateResume(jobId) {
    const button = document.querySelector(`[onclick="generateResume(${jobId})"]`);
    const btnText = button.querySelector('.btn-text');
    const btnLoading = button.querySelector('.btn-loading');
    
    // Show loading state
    btnText.classList.add('d-none');
    btnLoading.classList.remove('d-none');
    button.disabled = true;
    
    // Create a temporary link to trigger download
    const link = document.createElement('a');
    link.href = `/api/generate-resume/${jobId}`;
    link.download = '';  // Let the server set the filename
    link.style.display = 'none';
    
    // Handle the download
    fetch(`/api/generate-resume/${jobId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(async response => {
        if (response.ok && response.headers.get('content-type')?.includes('wordprocessingml')) {
            // Success - trigger download
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            
            // Get filename from content-disposition header
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'resume.docx';
            if (contentDisposition) {
                const matches = contentDisposition.match(/filename="([^"]+)"/);
                if (matches) {
                    filename = matches[1];
                }
            }
            
            // Create download link
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            // Clean up
            window.URL.revokeObjectURL(url);
            
            showNotification('success', `Resume generated successfully: ${filename}`);
        } else {
            // Error response
            const errorData = await response.json();
            showNotification('error', errorData.message || 'Error generating resume');
        }
    })
    .catch(error => {
        showNotification('error', 'Error generating resume: ' + error.message);
    })
    .finally(() => {
        // Reset button state
        btnText.classList.remove('d-none');
        btnLoading.classList.add('d-none');
        button.disabled = false;
    });
}

// Job action functions
function markAsApplied(jobId) {
    showLoading('Marking job as applied...');
    
    fetch(`/api/mark-applied/${jobId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        
        if (data.success) {
            showNotification('success', data.message);
            // Remove the job card from the page
            const jobCard = document.querySelector(`[data-job-id="${jobId}"]`);
            if (jobCard) {
                jobCard.style.transition = 'opacity 0.3s';
                jobCard.style.opacity = '0';
                setTimeout(() => {
                    jobCard.remove();
                    // Update the job count
                    updateJobCount();
                }, 300);
            }
        } else {
            showNotification('error', data.message);
        }
    })
    .catch(error => {
        hideLoading();
        showNotification('error', 'Error marking job as applied: ' + error.message);
    });
}

function deleteJob(jobId) {
    if (!confirm('Are you sure you want to delete this job? This action cannot be undone.')) {
        return;
    }
    
    showLoading('Deleting job...');
    
    fetch(`/api/delete-job/${jobId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        
        if (data.success) {
            showNotification('success', data.message);
            // Remove the job card from the page
            const jobCard = document.querySelector(`[data-job-id="${jobId}"]`);
            if (jobCard) {
                jobCard.style.transition = 'opacity 0.3s';
                jobCard.style.opacity = '0';
                setTimeout(() => {
                    jobCard.remove();
                    // Update the job count
                    updateJobCount();
                }, 300);
            }
        } else {
            showNotification('error', data.message);
        }
    })
    .catch(error => {
        hideLoading();
        showNotification('error', 'Error deleting job: ' + error.message);
    });
}

function updateJobCount() {
    const remainingJobs = document.querySelectorAll('.job-card').length;
    const countElement = document.querySelector('.card-title');
    if (countElement) {
        countElement.textContent = remainingJobs;
    }
}

// Collapse icon toggle - Dashboard specific
document.addEventListener('DOMContentLoaded', function() {
    const collapseButtons = document.querySelectorAll('[data-bs-toggle="collapse"]');
    collapseButtons.forEach(button => {
        const target = document.querySelector(button.getAttribute('data-bs-target'));
        if (target) {
            target.addEventListener('show.bs.collapse', function() {
                const chevron = button.querySelector('.bi-chevron-right');
                if (chevron) {
                    chevron.classList.remove('bi-chevron-right');
                    chevron.classList.add('bi-chevron-down');
                }
            });
            target.addEventListener('hide.bs.collapse', function() {
                const chevron = button.querySelector('.bi-chevron-down');
                if (chevron) {
                    chevron.classList.remove('bi-chevron-down');
                    chevron.classList.add('bi-chevron-right');
                }
            });
        }
    });
});

// Enhanced company website finder function with better error handling
function openCompanyWebsite(jobTitle, jobDescription) {
    try {
        // Extract company name from job title
        let companyName = extractCompanyName(jobTitle, jobDescription);
        
        if (!companyName) {
            showNotification('warning', 'Could not identify company name from job posting. Opening Google search instead.');
            // Fallback to general job search
            const searchQuery = jobTitle.split(' ').slice(0, 4).join(' ') + ' careers jobs';
            const googleUrl = `https://www.google.com/search?q=${encodeURIComponent(searchQuery)}`;
            window.open(googleUrl, '_blank');
            return;
        }
        
        showNotification('info', `Looking for ${companyName} careers page...`);
        
        // Skip direct URL attempts that cause 403 errors, go straight to intelligent search
        openCompanyCareerSearch(companyName);
        
    } catch (error) {
        console.error('Error finding company website:', error);
        showNotification('error', 'Error occurred while searching for company website.');
    }
}

// Intelligent company career search function
function openCompanyCareerSearch(companyName) {
    // Use multiple search strategies simultaneously
    
    // Primary: Google search for company careers
    const careerSearchQuery = `"${companyName}" careers jobs site:${companyName.toLowerCase().replace(/\s+/g, '')}.com OR site:careers.${companyName.toLowerCase().replace(/\s+/g, '')}.com OR site:jobs.${companyName.toLowerCase().replace(/\s+/g, '')}.com`;
    const googleCareerUrl = `https://www.google.com/search?q=${encodeURIComponent(careerSearchQuery)}`;
    
    // Fallback: broader search if the specific search doesn't work
    const broadSearchQuery = `"${companyName}" careers "current openings" OR "job opportunities" OR "apply now"`;
    const googleBroadUrl = `https://www.google.com/search?q=${encodeURIComponent(broadSearchQuery)}`;
    
    // Open the targeted search
    window.open(googleCareerUrl, '_blank');
    showNotification('success', `Opened targeted search for "${companyName}" careers page. This should find their job listings directly.`);
}

function extractCompanyName(jobTitle, jobDescription) {
    // Clean up job title and description for processing
    const title = jobTitle || '';
    const description = jobDescription || '';
    
    // Common patterns to extract company names from job titles
    const titlePatterns = [
        /at\s+([A-Z][a-zA-Z\s&.,]+?)(?:\s*[-|]|$)/i,
        /@\s*([A-Z][a-zA-Z\s&.,]+?)(?:\s*[-|]|$)/i,
        /-\s*([A-Z][a-zA-Z\s&.,]+?)(?:\s*[-|]|$)/i,
        /\|\s*([A-Z][a-zA-Z\s&.,]+?)(?:\s*[-|]|$)/i
    ];
    
    // Try to extract from job title first
    for (const pattern of titlePatterns) {
        const match = title.match(pattern);
        if (match && match[1]) {
            let company = match[1].trim();
            // Clean up common suffixes
            company = company.replace(/\s+(Inc|LLC|Corp|Ltd|Co)\.?$/i, '');
            company = company.replace(/\s+/g, ' ').trim();
            if (company.length > 2 && company.length < 50) {
                return company;
            }
        }
    }
    
    // Try to extract from description
    const descPatterns = [
        /(?:About|Join|At)\s+([A-Z][a-zA-Z\s&.,]+?)(?:\s*[,\n]|\s+is\s|\s+are\s)/i,
        /([A-Z][a-zA-Z\s&.,]+?)\s+is\s+(?:a\s+|an\s+)?(?:leading|growing|innovative|established)/i,
        /Company:\s*([A-Z][a-zA-Z\s&.,]+?)(?:\s*\n|$)/i
    ];
    
    for (const pattern of descPatterns) {
        const match = description.match(pattern);
        if (match && match[1]) {
            let company = match[1].trim();
            company = company.replace(/\s+(Inc|LLC|Corp|Ltd|Co)\.?$/i, '');
            company = company.replace(/\s+/g, ' ').trim();
            if (company.length > 2 && company.length < 50) {
                return company;
            }
        }
    }
    
    return null;
}

// Legacy functions - now using intelligent search approach
// Keeping these for potential future use but they're no longer called

function fallbackToGoogleSearch(companyName) {
    // Fall back to Google search
    const searchQuery = `${companyName} official website`;
    const googleUrl = `https://www.google.com/search?q=${encodeURIComponent(searchQuery)}`;
    window.open(googleUrl, '_blank');
    showNotification('info', `Opened Google search for "${companyName}" - look for their official website in the results.`);
}

// Additional search functions for dropdown options
function searchCompanyGoogle(jobTitle) {
    const companyName = extractCompanyName(jobTitle, '');
    if (companyName) {
        // Use the same intelligent search as the main button
        openCompanyCareerSearch(companyName);
    } else {
        const searchQuery = jobTitle.split(' ').slice(0, 4).join(' ') + ' careers jobs'; // Use first few words + careers jobs
        const googleUrl = `https://www.google.com/search?q=${encodeURIComponent(searchQuery)}`;
        window.open(googleUrl, '_blank');
        showNotification('info', 'Opened Google job search using job title');
    }
}

function searchCompanyLinkedIn(jobTitle) {
    const companyName = extractCompanyName(jobTitle, '');
    if (companyName) {
        // Search for company jobs on LinkedIn instead of just company page
        const jobSearchQuery = `${companyName}`;
        const linkedInUrl = `https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(jobSearchQuery)}&f_C=${encodeURIComponent(companyName)}`;
        window.open(linkedInUrl, '_blank');
        showNotification('info', `Opened LinkedIn jobs search for "${companyName}"`);
    } else {
        const searchQuery = jobTitle.split(' ').slice(0, 4).join(' '); // Use first few words
        const linkedInUrl = `https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(searchQuery)}`;
        window.open(linkedInUrl, '_blank');
        showNotification('info', 'Opened LinkedIn job search using job title');
    }
}