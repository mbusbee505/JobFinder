// JobFinder Frontend JavaScript

// WebSocket connection for real-time updates
let ws = null;

// Initialize WebSocket connection
function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = function(event) {
        console.log('WebSocket connected');
    };
    
    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
    
    ws.onclose = function(event) {
        console.log('WebSocket disconnected');
        // Attempt to reconnect after 5 seconds
        setTimeout(initWebSocket, 5000);
    };
    
    ws.onerror = function(error) {
        console.error('WebSocket error:', error);
    };
}

// Handle WebSocket messages
function handleWebSocketMessage(data) {
    switch(data.type) {
        case 'scan_started':
            updateScanStatus(true, data.message);
            showNotification('info', data.message);
            break;
        case 'scan_stopping':
            updateScanStatus('stopping', data.message);
            showNotification('warning', data.message);
            break;
        case 'scan_stopped':
            updateScanStatus(false, data.message);
            showNotification('info', data.message);
            break;
        case 'scan_complete':
            updateScanStatus(false, data.message);
            showNotification('success', `Scan complete! New jobs: ${data.new_jobs}, Links examined: ${data.links_examined}`);
            // Refresh the page to show new jobs
            setTimeout(() => location.reload(), 2000);
            break;
        case 'scan_error':
            updateScanStatus(false, data.message);
            showNotification('error', data.message);
            break;
        case 'job_updated':
            showNotification('success', data.message);
            break;
        case 'jobs_cleared':
            showNotification('info', data.message);
            // Refresh the page to reflect changes
            setTimeout(() => location.reload(), 1000);
            break;
        case 'jobs_archived':
            showNotification('info', data.message);
            // Refresh the page to reflect changes
            setTimeout(() => location.reload(), 1000);
            break;
    }
}

// Update scan status in UI
function updateScanStatus(status, message) {
    const startBtn = document.getElementById('start-scan-btn');
    const stopBtn = document.getElementById('stop-scan-btn');
    const scanMessage = document.getElementById('scan-message');
    
    if (startBtn && stopBtn) {
        if (status === true || status === 'running') {
            // Scan is running
            startBtn.disabled = true;
            stopBtn.disabled = false;
            stopBtn.textContent = '⏹️ Stop Scan';
            stopBtn.classList.remove('btn-secondary');
            stopBtn.classList.add('btn-danger');
        } else if (status === 'stopping') {
            // Scan is stopping
            startBtn.disabled = true;
            stopBtn.disabled = true;
            stopBtn.textContent = '⏳ Stopping...';
            stopBtn.classList.remove('btn-danger');
            stopBtn.classList.add('btn-secondary');
        } else {
            // Scan is stopped
            startBtn.disabled = false;
            stopBtn.disabled = true;
            stopBtn.textContent = '⏹️ Stop Scan';
            stopBtn.classList.remove('btn-secondary');
            stopBtn.classList.add('btn-danger');
        }
    }
    
    if (scanMessage && message) {
        scanMessage.textContent = message;
        scanMessage.classList.remove('d-none');
        
        // Update message styling based on status
        scanMessage.className = 'alert mb-2';
        if (status === true || status === 'running') {
            scanMessage.classList.add('alert-info');
        } else if (status === 'stopping') {
            scanMessage.classList.add('alert-warning');
        } else {
            scanMessage.classList.add('alert-success');
            
            // Hide success message after 5 seconds
            setTimeout(() => {
                scanMessage.classList.add('d-none');
            }, 5000);
        }
    }
}

// Subtle notification system - only shows critical messages
function showNotification(type, message) {
    // Only show critical errors and important success messages
    if (type === 'error' || (type === 'success' && (
        message.includes('saved successfully') ||
        message.includes('complete') ||
        message.includes('imported successfully') ||
        message.includes('exported successfully')
    ))) {
        showStatusMessage(type, message);
    }
    // Silently ignore info/warning messages and routine success messages
}

// Show brief status message for critical notifications only
function showStatusMessage(type, message) {
    const statusBar = document.getElementById('status-bar');
    const statusMessage = document.getElementById('status-message');
    
    if (!statusBar || !statusMessage) return;
    
    const alertClass = type === 'error' ? 'alert-danger' : 'alert-success';
    
    statusBar.className = `alert ${alertClass} alert-dismissible fade show mt-3`;
    statusMessage.textContent = message;
    statusBar.classList.remove('d-none');
    
    // Auto-dismiss after 3 seconds for non-errors, 6 seconds for errors
    const timeout = type === 'error' ? 6000 : 3000;
    setTimeout(() => {
        if (statusBar && !statusBar.classList.contains('d-none')) {
            statusBar.classList.add('d-none');
        }
    }, timeout);
}

// Job Management Functions
function startScan() {
    fetch('/api/start-scan', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (!data.success) {
            showNotification('error', data.message);
        }
        // Success message will come via WebSocket
    })
    .catch(error => {
        showNotification('error', 'Error starting scan: ' + error.message);
    });
}

function stopScan() {
    // Immediately show stopping state
    updateScanStatus('stopping', 'Requesting scan stop...');
    
    fetch('/api/stop-scan', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (!data.success) {
            showNotification('error', data.message);
            // Reset UI on error
            updateScanStatus(false, 'Error stopping scan');
        } else {
            showNotification('info', data.message);
        }
        // Success message will come via WebSocket
    })
    .catch(error => {
        showNotification('error', 'Error stopping scan: ' + error.message);
        // Reset UI on error
        updateScanStatus(false, 'Error stopping scan');
    });
}

function clearAllJobs() {
    if (!confirm('Are you sure you want to clear all approved jobs? This action cannot be undone.')) {
        return;
    }
    
    fetch('/api/clear-jobs', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (!data.success) {
            showNotification('error', data.message);
        }
        // Success message will come via WebSocket
    })
    .catch(error => {
        showNotification('error', 'Error clearing jobs: ' + error.message);
    });
}

// Database Management Functions
function showDbUploader() {
    document.getElementById('db-file-input').click();
}

function importDatabase() {
    const fileInput = document.getElementById('db-file-input');
    const file = fileInput.files[0];
    
    if (!file) return;
    
    const formData = new FormData();
    formData.append('db_file', file);
    
    showLoading('Importing database...');
    
    fetch('/api/import-database', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showNotification('success', data.message);
            // Refresh page after successful import
            setTimeout(() => location.reload(), 2000);
        } else {
            showNotification('error', data.message);
        }
    })
    .catch(error => {
        hideLoading();
        showNotification('error', 'Error importing database: ' + error.message);
    })
    .finally(() => {
        fileInput.value = ''; // Clear the file input
    });
}

function reloadConfig() {
    fetch('/api/reload-config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('success', data.message || 'Configuration reloaded successfully');
        } else {
            showNotification('error', data.message || 'Failed to reload configuration');
        }
    })
    .catch(error => {
        showNotification('error', 'Error reloading configuration: ' + error.message);
    });
}

// Loading overlay functions
function showLoading(message) {
    const overlay = document.getElementById('loading-overlay');
    const messageElement = document.getElementById('loading-message');
    
    if (overlay && messageElement) {
        messageElement.textContent = message || 'Processing...';
        overlay.classList.remove('d-none');
        overlay.classList.add('d-flex');
    }
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.classList.add('d-none');
        overlay.classList.remove('d-flex');
    }
}

// Form submission helper
function submitForm(formId, endpoint, successMessage) {
    const form = document.getElementById(formId);
    if (!form) return;
    
    const formData = new FormData(form);
    
    showLoading('Saving...');
    
    fetch(endpoint, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.success) {
            showNotification('success', successMessage || data.message);
        } else {
            showNotification('error', data.message);
        }
    })
    .catch(error => {
        hideLoading();
        showNotification('error', 'Error: ' + error.message);
    });
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize WebSocket connection
    initWebSocket();
    
    // Set up form submissions
    const configForm = document.getElementById('config-form');
    if (configForm) {
        configForm.addEventListener('submit', function(e) {
            e.preventDefault();
            submitForm('config-form', '/api/save-config', 'Configuration saved successfully!');
        });
    }
    
    // Set up any other page-specific initialization
    console.log('JobFinder application initialized');
}); 