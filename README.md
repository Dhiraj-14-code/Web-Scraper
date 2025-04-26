# Web-Scraper
A modular web scraping system using Flask, BeautifulSoup, and Selenium to extract and display real-time data from various websites. Users can select categories, scrape data efficiently, store it in MySQL, and view it through a responsive web interface built with HTML, CSS, and JavaScript.
Here’s a clean and short **README.md** for your project:

---

# Web Scraper 

A modular web scraping application built with Flask, BeautifulSoup, and Selenium. It allows users to scrape real-time data from various websites, store it in MySQL, and view it dynamically through a responsive web interface.

## Features
- Category-based data scraping
- Real-time extraction and rendering
- Structured storage using MySQL
- Dynamic frontend with HTML, CSS, JavaScript
- Error handling for different website structures

## Tech Stack
- **Frontend:** HTML, CSS, JavaScript
- **Backend:** Flask (Python)
- **Scraping Tools:** BeautifulSoup, Selenium
- **Database:** MySQL

## Setup Instructions
1. Clone the repository.
2. Set up a MySQL database and update your database credentials in `db.py`.
3. Install dependencies:  
   ```
   pip install -r requirements.txt
   ```
4. Run the Flask server:  
   ```
   python app.py
   ```
5. Open your browser and navigate to `http://localhost:5000/`.

## Requirements
- Python 3.x
- MySQL Server
- Required Python packages (Flask, BeautifulSoup, Selenium)

## License
This project is for educational purposes only.

