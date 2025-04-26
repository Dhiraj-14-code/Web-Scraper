import logging
from scraper import scrape_website

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_scraping():
    # Test URL
    url = "https://example.com"
    
    print("\nTesting static scraping...")
    try:
        result = scrape_website(url, method='static', elements=['title', 'headings'])
        print("Static scraping result:", result)
    except Exception as e:
        print("Static scraping error:", str(e))
    
    print("\nTesting dynamic scraping...")
    try:
        result = scrape_website(url, method='dynamic', elements=['title', 'headings'])
        print("Dynamic scraping result:", result)
    except Exception as e:
        print("Dynamic scraping error:", str(e))

if __name__ == "__main__":
    test_scraping() 