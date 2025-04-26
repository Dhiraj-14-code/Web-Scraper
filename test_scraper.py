from scraper import scrape_website
import json

def test_scrape():
    print("Testing scraper...")
    try:
        result = scrape_website(url="https://www.example.com", method="static")
        print("Scraping result:")
        print(json.dumps(result, indent=2))
        return True
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    test_scrape() 