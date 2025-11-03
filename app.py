# app.py
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import sqlite3
from datetime import datetime
import json
import traceback

# Import our modules
import database
import utils
from config import load, save_config, get_available_presets, save_preset, load_preset, apply_preset, delete_preset, create_default_presets
from utils import start_scan, stop_scan, get_scan_status

app = Flask(__name__)
app.secret_key = 'jobfinder-secret-key-change-in-production'

# Initialize database on startup
utils.ensure_database_initialized()

@app.route('/')
def dashboard():
    """Main dashboard showing approved jobs"""
    try:
        with database.get_conn() as conn:
            # Get approved jobs with job details
            query = """
            SELECT
                a.id as approved_id,
                a.date_approved,
                a.reason,
                a.date_applied,
                a.is_archived,
                d.job_id,
                d.title,
                d.url,
                d.location,
                d.keyword,
                d.description
            FROM approved_jobs a
            JOIN discovered_jobs d ON a.discovered_job_id = d.id
            WHERE (a.is_archived IS NULL OR a.is_archived = FALSE)
            ORDER BY a.date_approved DESC
            """
            approved_jobs = conn.execute(query).fetchall()

            # Get summary statistics
            stats_query = """
            SELECT
                COUNT(*) as total_discovered,
                (SELECT COUNT(*) FROM approved_jobs WHERE is_archived IS NULL OR is_archived = FALSE) as total_approved,
                (SELECT COUNT(*) FROM approved_jobs WHERE date_applied IS NOT NULL AND (is_archived IS NULL OR is_archived = FALSE)) as total_applied,
                (SELECT COUNT(*) FROM discovered_jobs WHERE analyzed = TRUE) as total_analyzed
            FROM discovered_jobs
            """
            stats = conn.execute(stats_query).fetchone()

        return render_template('dashboard.html',
                             jobs=approved_jobs,
                             stats=stats,
                             scan_status=get_scan_status())

    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template('dashboard.html', jobs=[], stats=None, scan_status=get_scan_status())

@app.route('/api/scan/start', methods=['POST'])
def api_start_scan():
    """Start the job scanning process"""
    success, message = start_scan()
    return jsonify({'success': success, 'message': message})

@app.route('/api/scan/stop', methods=['POST'])
def api_stop_scan():
    """Stop the job scanning process"""
    success, message = stop_scan()
    return jsonify({'success': success, 'message': message})

@app.route('/api/scan/status')
def api_scan_status():
    """Get current scan status"""
    return jsonify(get_scan_status())

@app.route('/api/job/<int:approved_id>/apply', methods=['POST'])
def mark_job_applied(approved_id):
    """Mark a job as applied"""
    try:
        success = database.mark_job_as_applied(approved_id)
        if success:
            return jsonify({'success': True, 'message': 'Job marked as applied'})
        else:
            return jsonify({'success': False, 'message': 'Job was already applied or not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/job/<int:approved_id>/delete', methods=['POST'])
def delete_approved_job(approved_id):
    """Delete an approved job"""
    try:
        success = database.delete_approved_job(approved_id)
        if success:
            return jsonify({'success': True, 'message': 'Job deleted'})
        else:
            return jsonify({'success': False, 'message': 'Job not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/jobs/archive-applied', methods=['POST'])
def archive_applied_jobs():
    """Archive all applied jobs"""
    try:
        count = database.archive_all_applied_jobs()
        return jsonify({'success': True, 'message': f'Archived {count} applied jobs'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/jobs/clear-approved', methods=['POST'])
def clear_all_approved():
    """Clear all approved jobs"""
    try:
        count = database.clear_all_approved_jobs()
        return jsonify({'success': True, 'message': f'Cleared {count} approved jobs'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/jobs/clear-discovered', methods=['POST'])
def clear_all_discovered():
    """Clear all discovered jobs - complete fresh start"""
    try:
        count = database.clear_all_discovered_jobs()
        return jsonify({'success': True, 'message': f'Cleared {count} discovered jobs - fresh start ready!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/config')
def config_page():
    """Configuration management page"""
    try:
        config = load()
        project_info = utils.get_project_info()
        presets = get_available_presets()

        return render_template('config.html', config=config, project_info=project_info, presets=presets)
    except Exception as e:
        flash(f'Error loading configuration: {str(e)}', 'error')
        return render_template('config.html', config={}, project_info={}, presets=[])

@app.route('/api/config/save', methods=['POST'])
def save_config_api():
    """Save configuration changes"""
    try:
        config_data = request.json

        # Basic validation
        if not config_data:
            return jsonify({'success': False, 'message': 'No configuration data provided'})

        # Validate required sections
        required_sections = ['search_parameters', 'api_keys', 'general']
        for section in required_sections:
            if section not in config_data:
                return jsonify({'success': False, 'message': f'Missing required section: {section}'})

        # Save the configuration
        save_config(config_data)

        return jsonify({'success': True, 'message': 'Configuration saved successfully'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error saving configuration: {str(e)}'})

# Preset management API routes
@app.route('/api/presets/list')
def api_list_presets():
    """Get list of available presets"""
    try:
        presets = get_available_presets()
        return jsonify({'success': True, 'presets': presets})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error loading presets: {str(e)}'})

@app.route('/api/presets/save', methods=['POST'])
def api_save_preset():
    """Save current configuration as a preset"""
    try:
        data = request.json
        preset_name = data.get('name', '').strip()
        display_name = data.get('display_name', '').strip()
        description = data.get('description', '').strip()

        if not preset_name:
            return jsonify({'success': False, 'message': 'Preset name is required'})

        # Get current configuration
        current_config = load()

        # Save the preset
        success = save_preset(preset_name, current_config, display_name, description)

        if success:
            return jsonify({'success': True, 'message': f'Preset "{display_name or preset_name}" saved successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to save preset'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error saving preset: {str(e)}'})

@app.route('/api/presets/load/<preset_name>')
def api_load_preset(preset_name):
    """Load a specific preset configuration"""
    try:
        preset_data = load_preset(preset_name)
        if preset_data:
            return jsonify({'success': True, 'preset': preset_data})
        else:
            return jsonify({'success': False, 'message': 'Preset not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error loading preset: {str(e)}'})

@app.route('/api/presets/apply/<preset_name>', methods=['POST'])
def api_apply_preset(preset_name):
    """Apply a preset as the current configuration"""
    try:
        success = apply_preset(preset_name)
        if success:
            # Get the preset info for display name
            preset_data = load_preset(preset_name)
            display_name = preset_data.get('metadata', {}).get('display_name', preset_name) if preset_data else preset_name
            return jsonify({'success': True, 'message': f'Applied preset "{display_name}" successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to apply preset'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error applying preset: {str(e)}'})

@app.route('/api/presets/delete/<preset_name>', methods=['POST'])
def api_delete_preset(preset_name):
    """Delete a preset"""
    try:
        # Get preset info before deleting for display name
        preset_data = load_preset(preset_name)
        display_name = preset_data.get('metadata', {}).get('display_name', preset_name) if preset_data else preset_name

        success = delete_preset(preset_name)
        if success:
            return jsonify({'success': True, 'message': f'Deleted preset "{display_name}" successfully'})
        else:
            return jsonify({'success': False, 'message': 'Preset not found'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error deleting preset: {str(e)}'})

@app.route('/api/presets/delete-all', methods=['POST'])
def api_delete_all_presets():
    """Delete all presets"""
    try:
        # Get all presets first
        presets = get_available_presets()
        deleted_count = 0

        # Delete each preset
        for preset in presets:
            if delete_preset(preset['name']):
                deleted_count += 1

        return jsonify({'success': True, 'message': f'Deleted {deleted_count} presets successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error deleting presets: {str(e)}'})

@app.route('/api/presets/create-defaults', methods=['POST'])
def api_create_default_presets():
    """Create default presets"""
    try:
        create_default_presets()
        presets = get_available_presets()
        return jsonify({'success': True, 'message': f'Created {len(presets)} default presets'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error creating default presets: {str(e)}'})

@app.route('/job/<int:job_id>')
def job_detail(job_id):
    """Job detail page"""
    try:
        with database.get_conn() as conn:
            query = """
            SELECT
                a.id as approved_id,
                a.date_approved,
                a.reason,
                a.date_applied,
                a.is_archived,
                d.job_id,
                d.title,
                d.url,
                d.location,
                d.keyword,
                d.description,
                d.date_discovered
            FROM approved_jobs a
            JOIN discovered_jobs d ON a.discovered_job_id = d.id
            WHERE d.job_id = ?
            """
            job = conn.execute(query, (job_id,)).fetchone()

            if not job:
                flash('Job not found', 'error')
                return redirect(url_for('dashboard'))

            return render_template('job_detail.html', job=job)

    except Exception as e:
        flash(f'Error loading job details: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/statistics')
def statistics_page():
    """Statistics and analytics page"""
    try:
        # Get comprehensive statistics using database function
        statistics = database.get_job_statistics()

        return render_template('statistics.html',
                             statistics=statistics,
                             scan_status=get_scan_status())

    except Exception as e:
        flash(f'Error loading statistics: {str(e)}', 'error')
        empty_stats = {
            'basic': {'total_discovered': 0, 'total_analyzed': 0, 'total_with_details': 0},
            'approved': {'total_approved': 0, 'total_applied': 0, 'total_archived': 0},
            'by_location': [],
            'by_keyword': [],
            'recent_activity': []
        }
        return render_template('statistics.html', statistics=empty_stats, scan_status=get_scan_status())

@app.route('/applied')
def archived_page():
    """Applied jobs page"""
    try:
        archived_jobs = database.get_archived_jobs()
        return render_template('archived.html',
                             jobs=archived_jobs,
                             scan_status=get_scan_status())
    except Exception as e:
        flash(f'Error loading applied jobs: {str(e)}', 'error')
        return render_template('archived.html', jobs=[], scan_status=get_scan_status())

@app.route('/logs')
def logs_page():
    """Logs and system information page"""
    try:
        # Get recent database activity
        with database.get_conn() as conn:
            recent_discovered = conn.execute("""
                SELECT job_id, title, url, location, date_discovered, analyzed
                FROM discovered_jobs
                ORDER BY date_discovered DESC
                LIMIT 50
            """).fetchall()

            recent_approved = conn.execute("""
                SELECT
                    a.date_approved,
                    a.reason,
                    d.job_id,
                    d.title,
                    d.url
                FROM approved_jobs a
                JOIN discovered_jobs d ON a.discovered_job_id = d.id
                ORDER BY a.date_approved DESC
                LIMIT 20
            """).fetchall()

        return render_template('logs.html',
                             recent_discovered=recent_discovered,
                             recent_approved=recent_approved,
                             scan_status=get_scan_status(),
                             project_info=utils.get_project_info())

    except Exception as e:
        flash(f'Error loading logs: {str(e)}', 'error')
        return render_template('logs.html', recent_discovered=[], recent_approved=[])

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# Template filters for better formatting
@app.template_filter('datetime_format')
def datetime_format(value):
    """Format datetime for display - outputs ISO format for client-side conversion"""
    if value is None:
        return ''
    if isinstance(value, str):
        try:
            # Parse the datetime and ensure it has UTC timezone info
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            # Return ISO format with Z suffix to indicate UTC
            return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        except:
            return value
    return value

@app.template_filter('truncate_text')
def truncate_text(text, length=100):
    """Truncate text to specified length"""
    if not text:
        return ''
    return text[:length] + '...' if len(text) > length else text

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8734)