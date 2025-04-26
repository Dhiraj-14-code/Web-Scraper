# Web Scraper Application

A Flask-based web application for scraping websites with user authentication and scheduling capabilities.

## Features

- User authentication (local and OAuth)
- Website scraping with multiple methods
- Scraping history tracking
- Scheduled scraping jobs
- Data export functionality
- User profile management

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd web-scraper
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
```
Edit the `.env` file with your configuration values.

## Running the Application

1. Activate the virtual environment (if not already activated):
```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Run the Flask application:
```bash
python app.py
```

3. Open your web browser and navigate to:
```
http://localhost:5000
```

## Database

The application uses SQLite as its database. The database file (`scraper.db`) will be automatically created when you first run the application.

## OAuth Setup

To use Google and Facebook login:

1. Create a project in the Google Cloud Console and get your OAuth credentials
2. Create a Facebook App and get your App ID and Secret
3. Add these credentials to your `.env` file

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 