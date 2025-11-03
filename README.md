# JobFinder2

An AI-powered job discovery system that automatically scrapes LinkedIn job postings, evaluates them using OpenAI's O3 model, and provides a web interface for managing job applications.

## Features

- **Automated LinkedIn Scraping**: Searches LinkedIn for jobs based on configured keywords and locations
- **AI-Powered Evaluation**: Uses OpenAI O3 model to evaluate job postings against your criteria
- **Web Interface**: Clean, modern web dashboard for managing jobs and configuration
- **Job Management**: Track applications, archive jobs, and manage your job pipeline
- **Configuration Management**: Easy-to-use web interface for updating settings

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure OpenAI API Key**
   - Start the application (see step 3)
   - Go to Configuration page
   - Add your OpenAI API key
   - Update search parameters and resume text

3. **Start the Application**
   ```bash
   python app.py
   ```
   Open your browser to http://localhost:5000

4. **Configure Your Settings**
   - Click "Configuration" in the navigation
   - Add your OpenAI API key
   - Set your preferred job locations and keywords
   - Add exclusion keywords for jobs you don't want
   - Paste your resume text for AI evaluation
   - Save the configuration

5. **Start Job Discovery**
   - Go back to the Dashboard
   - Click "Start Scan" to begin discovering jobs
   - The system will automatically scrape, evaluate, and approve relevant jobs

## Project Structure

```
JobFinder2/
├── app.py              # Main Flask web application
├── config.py           # Configuration management
├── database.py         # SQLite database operations
├── scrape.py          # LinkedIn scraping logic
├── evaluate.py        # AI job evaluation
├── utils.py           # Utility functions and path management
├── requirements.txt   # Python dependencies
├── config.toml        # Configuration file (auto-generated)
├── data/              # Database storage
├── templates/         # HTML templates
└── static/           # CSS and JavaScript files
```

## Configuration

The application uses a `config.toml` file for configuration. Key settings include:

- **Search Parameters**: Locations, keywords, and exclusions
- **API Keys**: OpenAI API key for job evaluation
- **Resume**: Your resume text for AI comparison
- **Evaluation Criteria**: Custom prompts for job evaluation

## Database

The application uses SQLite for local storage with the following tables:

- `discovered_jobs`: All scraped job postings
- `approved_jobs`: Jobs approved by AI evaluation
- `scan_control`: System control flags

## Important Notes

- **LinkedIn Terms of Service**: Be aware that automated scraping may violate LinkedIn's ToS
- **Rate Limiting**: The scraper includes delays and retry logic to avoid being blocked
- **API Costs**: OpenAI O3 API usage will incur costs based on your usage
- **Local Storage**: All data is stored locally in SQLite database

## Usage Tips

1. **Start Small**: Begin with a few specific keywords and locations to test the system
2. **Refine Exclusions**: Add exclusion keywords to filter out unwanted job types
3. **Monitor Costs**: Keep track of your OpenAI API usage as job evaluation can add up
4. **Regular Maintenance**: Periodically archive applied jobs to keep your dashboard clean

## Troubleshooting

- **Port Already in Use**: If port 5000 is in use, modify the port in `app.py`
- **Database Issues**: Delete the `data/jobfinder.db` file to reset the database
- **Configuration Problems**: Delete `config.toml` to regenerate with defaults

## Security

- Your OpenAI API key is stored in the local configuration file
- All data is stored locally on your machine
- No data is transmitted to external services except OpenAI for job evaluation

## Development

The application is built with:
- **Backend**: Flask (Python)
- **Frontend**: Bootstrap 5 + Custom CSS/JavaScript
- **Database**: SQLite
- **AI Integration**: OpenAI API
- **Web Scraping**: Requests + BeautifulSoup

For development, run with debug mode enabled in `app.py`.