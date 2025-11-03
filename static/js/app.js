// JobFinder Modern Web Application JavaScript

// Global state management
const AppState = {
    scanStatus: { is_running: false, stop_requested: false },
    scanInterval: null,
    notifications: new Set(),
    theme: localStorage.getItem('jobfinder-theme') || 'auto'
};

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

// Application initialization
function initializeApp() {
    initializeTheme();
    initializeScanStatus();
    startScanStatusPolling();
    initializeAnimations();
    initializeTooltips();
    convertAllTimestamps();

    console.log('🚀 JobFinder application initialized');
}

// Timestamp conversion utilities
function formatLocalDateTime(utcTimestamp) {
    if (!utcTimestamp || utcTimestamp === '') return 'Never';

    try {
        const date = new Date(utcTimestamp);
        if (isNaN(date.getTime())) return utcTimestamp;

        // Format: YYYY-MM-DD HH:MM:SS (in local timezone)
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');

        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
    } catch (error) {
        console.error('Error formatting timestamp:', error);
        return utcTimestamp;
    }
}

function convertAllTimestamps() {
    // Find all elements with timestamps and convert them
    document.querySelectorAll('[data-utc-timestamp]').forEach(element => {
        const utcTimestamp = element.getAttribute('data-utc-timestamp');
        element.textContent = formatLocalDateTime(utcTimestamp);
    });
}

// Theme management with 3-way toggle: light → dark → auto (system)
function initializeTheme() {
    applyTheme(AppState.theme);
    updateThemeIcon(AppState.theme);

    // Listen for system theme changes when in auto mode
    if (window.matchMedia) {
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        mediaQuery.addListener(() => {
            if (AppState.theme === 'auto') {
                applyTheme('auto');
            }
        });
    }
}

function applyTheme(theme) {
    let actualTheme = theme;

    if (theme === 'auto') {
        // Use system preference
        actualTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    if (actualTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
}

function updateThemeIcon(theme) {
    const themeIcon = document.getElementById('theme-icon');
    if (themeIcon) {
        switch (theme) {
            case 'light':
                themeIcon.className = 'bi bi-sun-fill';
                break;
            case 'dark':
                themeIcon.className = 'bi bi-moon-fill';
                break;
            case 'auto':
                themeIcon.className = 'bi bi-circle-half';
                break;
        }
    }
}

function toggleTheme() {
    // Three-way toggle: light → dark → auto → light
    let newTheme;
    switch (AppState.theme) {
        case 'light':
            newTheme = 'dark';
            break;
        case 'dark':
            newTheme = 'auto';
            break;
        case 'auto':
        default:
            newTheme = 'light';
            break;
    }

    AppState.theme = newTheme;
    localStorage.setItem('jobfinder-theme', newTheme);
    applyTheme(newTheme);
    updateThemeIcon(newTheme);

    // Theme switched silently - no notification needed
}

// Enhanced scan management with better UX
async function startScan() {
    const startBtn = document.getElementById('start-scan') || document.getElementById('start-scan-logs');
    const stopBtn = document.getElementById('stop-scan') || document.getElementById('stop-scan-logs');

    // Add loading state to button
    if (startBtn) {
        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Starting...';
    }

    try {
        const response = await fetch('/api/scan/start', { method: 'POST' });
        const result = await response.json();

        if (result.success) {
            showNotification('🚀 Job discovery started successfully!', 'success');
            updateScanButtons(true);

            // Add pulse animation to status indicator
            const statusBadge = document.querySelector('#scan-status .badge');
            if (statusBadge) {
                statusBadge.style.animation = 'pulse-subtle 2s ease-in-out infinite';
            }
        } else {
            showNotification(result.message, 'error');
        }
    } catch (error) {
        showNotification('Failed to start scan: ' + error.message, 'error');
        console.error('Scan start error:', error);
    } finally {
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.innerHTML = '<i class="bi bi-play-fill"></i> Start Discovery';
        }
    }
}

async function stopScan() {
    const stopBtn = document.getElementById('stop-scan') || document.getElementById('stop-scan-logs');

    if (stopBtn) {
        stopBtn.disabled = true;
        stopBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Stopping...';
    }

    try {
        const response = await fetch('/api/scan/stop', { method: 'POST' });
        const result = await response.json();

        if (result.success) {
            showNotification('🛑 Scan stopped successfully', 'info');
            updateScanButtons(false);
        } else {
            showNotification(result.message, 'error');
        }
    } catch (error) {
        showNotification('Failed to stop scan: ' + error.message, 'error');
        console.error('Scan stop error:', error);
    } finally {
        if (stopBtn) {
            stopBtn.disabled = false;
            stopBtn.innerHTML = '<i class="bi bi-stop-fill"></i> Stop Scan';
        }
    }
}

// Enhanced scan status management
async function updateScanStatus() {
    try {
        const response = await fetch('/api/scan/status');
        const status = await response.json();

        AppState.scanStatus = status;
        updateScanStatusDisplay(status);
        updateScanButtons(status.is_running);

        return status;
    } catch (error) {
        console.error('Error fetching scan status:', error);
        const fallbackStatus = { is_running: false, stop_requested: false };
        AppState.scanStatus = fallbackStatus;
        updateScanStatusDisplay(fallbackStatus);
        return fallbackStatus;
    }
}

function updateScanStatusDisplay(status) {
    const statusElement = document.getElementById('scan-status');
    const currentStatusElement = document.getElementById('current-status');

    const targetElement = statusElement || currentStatusElement;
    if (!targetElement) return;

    let statusConfig = getStatusConfig(status);

    // Update the badge
    const badge = targetElement.querySelector('.badge') || targetElement;
    const icon = badge.querySelector('i');

    if (badge) {
        badge.textContent = '';
        badge.className = `badge ${statusConfig.class}`;

        // Add icon and text
        badge.innerHTML = `
            <i class="bi ${statusConfig.icon} me-1" style="font-size: 0.5rem;"></i>
            ${statusConfig.text}
        `;

        // Add animation for active states
        if (status.is_running) {
            badge.style.animation = 'pulse-subtle 2s ease-in-out infinite';
        } else {
            badge.style.animation = 'none';
        }
    }
}

function getStatusConfig(status) {
    if (status.is_running && status.stop_requested) {
        return {
            text: 'Stopping',
            class: 'bg-warning',
            icon: 'bi-clock-fill'
        };
    } else if (status.is_running) {
        return {
            text: 'Discovering',
            class: 'bg-success',
            icon: 'bi-play-fill'
        };
    } else if (status.stop_requested) {
        return {
            text: 'Stopped',
            class: 'bg-secondary',
            icon: 'bi-pause-fill'
        };
    } else {
        return {
            text: 'Ready',
            class: 'bg-secondary',
            icon: 'bi-circle-fill'
        };
    }
}

function updateScanButtons(isRunning) {
    const startBtn = document.getElementById('start-scan') || document.getElementById('start-scan-logs');
    const stopBtn = document.getElementById('stop-scan') || document.getElementById('stop-scan-logs');

    if (startBtn && stopBtn) {
        if (isRunning) {
            startBtn.style.display = 'none';
            stopBtn.style.display = 'inline-flex';
        } else {
            startBtn.style.display = 'inline-flex';
            stopBtn.style.display = 'none';
        }
    }
}

// Enhanced notification system
function showNotification(message, type = 'info', duration = 5000) {
    // Remove existing notifications of the same type
    document.querySelectorAll(`.notification-toast.alert-${getAlertClass(type)}`).forEach(toast => {
        toast.remove();
    });

    const notificationId = Date.now().toString();
    AppState.notifications.add(notificationId);

    const alertClass = getAlertClass(type);
    const icon = getAlertIcon(type);

    const notification = document.createElement('div');
    notification.id = `notification-${notificationId}`;
    notification.className = `alert ${alertClass} alert-dismissible notification-toast position-fixed slide-up`;

    // Enhanced styling with dark mode support
    Object.assign(notification.style, {
        top: '20px',
        right: '20px',
        zIndex: '9999',
        minWidth: '350px',
        maxWidth: '500px',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-xl)',
        backdropFilter: 'blur(10px)',
        border: 'none',
        backgroundColor: document.documentElement.getAttribute('data-theme') === 'dark' ?
            (type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6') :
            undefined
    });

    notification.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="bi ${icon} me-3 flex-shrink-0" style="font-size: 1.2rem;"></i>
            <div class="flex-grow-1">
                <div class="fw-medium">${message}</div>
                ${type === 'error' ? '<small class="text-muted">Check the console for more details</small>' : ''}
            </div>
            <button type="button" class="btn-close ms-3" data-bs-dismiss="alert"></button>
        </div>
    `;

    // Add to DOM with entrance animation
    document.body.appendChild(notification);
    requestAnimationFrame(() => {
        notification.style.transform = 'translateX(0)';
    });

    // Auto-dismiss logic
    if (type !== 'error' && duration > 0) {
        setTimeout(() => {
            const alert = bootstrap.Alert.getInstance(notification);
            if (alert) {
                alert.close();
            }
            AppState.notifications.delete(notificationId);
        }, duration);
    }

    // Manual dismiss handler
    notification.addEventListener('closed.bs.alert', () => {
        AppState.notifications.delete(notificationId);
    });
}

function getAlertClass(type) {
    const classes = {
        'success': 'alert-success',
        'error': 'alert-danger',
        'warning': 'alert-warning',
        'info': 'alert-info'
    };
    return classes[type] || 'alert-info';
}

function getAlertIcon(type) {
    const icons = {
        'success': 'bi-check-circle-fill',
        'error': 'bi-exclamation-triangle-fill',
        'warning': 'bi-exclamation-triangle-fill',
        'info': 'bi-info-circle-fill'
    };
    return icons[type] || 'bi-info-circle-fill';
}

// Modern loading management
function showGlobalLoading(message = 'Processing...') {
    hideGlobalLoading(); // Remove any existing loading

    const loading = document.createElement('div');
    loading.id = 'global-loading';
    loading.className = 'loading-overlay fade-in';
    loading.innerHTML = `
        <div class="bg-white rounded-4 p-5 text-center shadow-lg" style="min-width: 200px;">
            <div class="spinner mb-4"></div>
            <h6 class="text-gray-700 mb-0">${message}</h6>
        </div>
    `;

    document.body.appendChild(loading);
}

function hideGlobalLoading() {
    const loading = document.getElementById('global-loading');
    if (loading) {
        loading.style.opacity = '0';
        setTimeout(() => loading.remove(), 150);
    }
}

// Enhanced utility functions
function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(() => {
            showNotification('📋 Copied to clipboard!', 'success', 2000);
        }).catch(() => {
            fallbackCopyToClipboard(text);
        });
    } else {
        fallbackCopyToClipboard(text);
    }
}

function fallbackCopyToClipboard(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.cssText = 'position:fixed;left:-999999px;top:-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    try {
        document.execCommand('copy');
        showNotification('📋 Copied to clipboard!', 'success', 2000);
    } catch (error) {
        showNotification('❌ Failed to copy to clipboard', 'error');
    } finally {
        document.body.removeChild(textArea);
    }
}

// Advanced animations and interactions
function initializeAnimations() {
    // Intersection Observer for scroll animations
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('animate-in');
                }
            });
        }, { threshold: 0.1 });

        // Observe elements that should animate on scroll
        document.querySelectorAll('.card, .stat-card').forEach(el => {
            observer.observe(el);
        });
    }
}

function initializeTooltips() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Scan status polling with intelligent intervals
function startScanStatusPolling() {
    if (AppState.scanInterval) clearInterval(AppState.scanInterval);

    const poll = () => {
        updateScanStatus().then(status => {
            // Use shorter intervals when scan is active
            const interval = status.is_running ? 3000 : 10000;

            if (AppState.scanInterval) clearInterval(AppState.scanInterval);
            AppState.scanInterval = setTimeout(poll, interval);
        });
    };

    poll(); // Initial call
}

function stopScanStatusPolling() {
    if (AppState.scanInterval) {
        clearTimeout(AppState.scanInterval);
        AppState.scanInterval = null;
    }
}

// Page lifecycle management
function initializeScanStatus() {
    updateScanStatus();
}

// Enhanced error handling
function handleApiError(error, defaultMessage = 'An unexpected error occurred') {
    console.error('API Error:', error);

    let message = defaultMessage;
    if (error.response) {
        message = `Server error: ${error.response.status}`;
    } else if (error.message) {
        message = error.message;
    }

    showNotification(message, 'error');
}

// Modern confirmation dialogs
function confirmAction(message, callback, options = {}) {
    const defaults = {
        title: 'Confirm Action',
        confirmText: 'Confirm',
        cancelText: 'Cancel',
        type: 'warning'
    };
    const config = { ...defaults, ...options };

    // For now, use native confirm - could be enhanced with custom modal
    if (confirm(message)) {
        callback();
    }
}

// Performance monitoring
function logPerformance(label, startTime) {
    const duration = performance.now() - startTime;
    console.log(`⚡ ${label}: ${duration.toFixed(2)}ms`);
}

// Page visibility handling for better performance
document.addEventListener('visibilitychange', function() {
    if (document.visibilityState === 'visible') {
        // Page is visible, resume polling
        startScanStatusPolling();
        console.log('📱 Page visible - resuming status polling');
    } else {
        // Page is hidden, reduce polling
        stopScanStatusPolling();
        console.log('📱 Page hidden - pausing status polling');
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    stopScanStatusPolling();
    console.log('👋 JobFinder cleanup completed');
});

// Global error handling
window.addEventListener('error', function(event) {
    console.error('Global error:', event.error);
    showNotification('An unexpected error occurred. Please refresh the page.', 'error');
});

// Export functions for global use and backwards compatibility
window.JobFinder = {
    startScan,
    stopScan,
    updateScanStatus,
    showNotification,
    copyToClipboard,
    showGlobalLoading,
    hideGlobalLoading,
    confirmAction,
    toggleTheme,
    AppState
};

// Make key functions available globally for onclick handlers
window.startScan = startScan;
window.stopScan = stopScan;
window.showNotification = showNotification;
window.toggleTheme = toggleTheme;