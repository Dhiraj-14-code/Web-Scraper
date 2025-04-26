from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import time
import logging
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from webdriver_manager.chrome import ChromeDriverManager
#from scraper import scrape_website

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebScraper:
    def __init__(self):
        # Configure retry strategy for requests
        self.retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        self.adapter = HTTPAdapter(max_retries=self.retry_strategy)
        self.session = requests.Session()
        self.session.mount("https://", self.adapter)
        self.session.mount("http://", self.adapter)
        
        # Initialize Chrome options
        self.chrome_options = Options()
        self.chrome_options.add_argument('--headless')
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.chrome_options.add_argument('--window-size=1366,768')
        self.chrome_options.add_argument('--disable-notifications')
        self.chrome_options.add_argument('--remote-debugging-port=9222')  # Debugging

        # Optimize page load strategy
        self.chrome_options.page_load_strategy = "eager"  # Load faster by waiting for DOM only

        # Add user agent
        self.chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

    def get_driver(self):
        """Initialize and return a Chrome WebDriver"""
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=self.chrome_options)
            return driver
        except WebDriverException as e:
            logger.error(f"Error initializing Chrome driver: {str(e)}")
            raise

    def scrape_static(self, url, elements=None):
        """Scrape website using requests and BeautifulSoup"""
        if elements is None:
            elements = ['title', 'headings', 'text', 'links', 'images', 'tables']
            
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            
            response = self.session.get(url, headers=headers, timeout=15)  # Reduced timeout
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            return self._process_content(soup, elements)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error in static scraping: {str(e)}")
            return {"error": str(e)}

    def scrape_dynamic(self, url, elements=None):
        """Scrape website using Selenium"""
        if elements is None:
            elements = ['title', 'headings', 'text', 'links', 'images', 'tables']
        
        driver = None
        try:
            driver = self.get_driver()
            driver.set_page_load_timeout(30)
            
            # Retry loading the page in case of timeout
            for attempt in range(3):  # Try 3 times
                try:
                    driver.get(url)
                    break
                except TimeoutException:
                    if attempt < 2:
                        logger.warning("Page load timeout, retrying...")
                    else:
                        raise TimeoutException("Failed to load page after multiple attempts")

            # Wait for the body tag to be present
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Ensure all content is loaded
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

            # Get page source and parse with BeautifulSoup
            soup = BeautifulSoup(driver.page_source, 'lxml')
            return self._process_content(soup, elements)
            
        except (TimeoutException, WebDriverException) as e:
            logger.error(f"Error in dynamic scraping: {str(e)}")
            return {"error": str(e)}
        finally:
            if driver:
                driver.quit()

    def _process_content(self, soup, elements):
        """Process the scraped content"""
        result = {}

        for element in elements:
            try:
                if element == 'title':
                    result['title'] = soup.title.string.strip() if soup.title else None
                
                elif element == 'headings':
                    result['headings'] = {
                        'h1': [h.text.strip() for h in soup.find_all('h1') if h.text.strip()],
                        'h2': [h.text.strip() for h in soup.find_all('h2') if h.text.strip()],
                        'h3': [h.text.strip() for h in soup.find_all('h3') if h.text.strip()]
                    }
                
                elif element == 'text':
                    result['text'] = [p.text.strip() for p in soup.find_all(['p', 'article', 'section']) 
                                    if p.text.strip() and len(p.text.strip()) > 20]
                
                elif element == 'links':
                    result['links'] = [
                        {'text': a.text.strip(), 'href': a.get('href')} 
                        for a in soup.find_all('a') 
                        if a.get('href') and a.text.strip()
                    ]
                
                elif element == 'images':
                    result['images'] = [
                        {'alt': img.get('alt', '').strip(), 'src': img.get('src')} 
                        for img in soup.find_all('img') 
                        if img.get('src')
                    ]
                
                elif element == 'tables':
                    result['tables'] = [
                        [[cell.text.strip() for cell in row.find_all(['td', 'th'])] 
                         for row in table.find_all('tr') if row.find_all(['td', 'th'])]
                        for table in soup.find_all('table')
                    ]
                    
            except Exception as e:
                logger.error(f"Error processing element {element}: {str(e)}")
                result[element] = None
        
        return result

def scrape_website(url, method='auto', elements=None):
    """Main scraping function"""
    scraper = WebScraper()
    
    try:
        if method == 'static':
            return scraper.scrape_static(url, elements)
        elif method == 'dynamic':
            return scraper.scrape_dynamic(url, elements)
        else:
            try:
                logger.info("Attempting static scraping...")
                return scraper.scrape_static(url, elements)
            except Exception as e:
                logger.info(f"Static scraping failed ({str(e)}), switching to dynamic...")
                return scraper.scrape_dynamic(url, elements)
    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}")
        return {"error": str(e), "message": "Failed to scrape the website", "url": url}
