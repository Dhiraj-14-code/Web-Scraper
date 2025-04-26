"""Configuration settings for the web scraper"""

# Scraping settings
SCRAPING_CONFIG = {
    'TIMEOUT': 30,  # Request timeout in seconds
    'MAX_RETRIES': 3,  # Maximum number of retry attempts
    'CONCURRENT_REQUESTS': 5,  # Maximum number of concurrent requests
    'USER_AGENTS': [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/89.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15',
    ],
    'DEFAULT_HEADERS': {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
    }
}

# Selenium settings
SELENIUM_CONFIG = {
    'PAGE_LOAD_TIMEOUT': 30,
    'IMPLICIT_WAIT': 10,
    'EXPLICIT_WAIT': 10,
    'CHROME_OPTIONS': [
        '--headless',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--disable-extensions',
        '--disable-infobars',
        '--disable-notifications',
        '--disable-images',  # Disable image loading for faster scraping
        '--blink-settings=imagesEnabled=false',
    ]
}

# Database settings
DB_CONFIG = {
    'POOL_SIZE': 5,  # Connection pool size
    'POOL_TIMEOUT': 30,  # Pool timeout in seconds
    'MAX_OVERFLOW': 10  # Maximum number of connections that can be created beyond pool_size
}

# Cache settings
CACHE_CONFIG = {
    'ENABLED': True,
    'EXPIRE_TIME': 3600,  # Cache expiration time in seconds
    'MAX_SIZE': 100  # Maximum number of items to cache
} 