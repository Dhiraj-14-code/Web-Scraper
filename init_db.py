import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'mysql123'),
    'database': os.getenv('DB_NAME', 'scraped_db')
}

def init_database():
    try:
        # First, connect without database to create it if it doesn't exist
        conn = mysql.connector.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password']
        )
        
        if conn.is_connected():
            cursor = conn.cursor()
            
            # Create database if it doesn't exist
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
            print(f"Database '{DB_CONFIG['database']}' created successfully")
            
            # Switch to the database
            cursor.execute(f"USE {DB_CONFIG['database']}")
            
            # Create users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    email VARCHAR(120) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_login DATETIME,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    INDEX idx_username (username),
                    INDEX idx_email (email)
                )
            ''')
            print("Users table created successfully")
            
            # Create scraping_history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scraping_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    url VARCHAR(500) NOT NULL,
                    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    elements TEXT,
                    results LONGTEXT,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    execution_time FLOAT,
                    method VARCHAR(20),
                    INDEX idx_url (url),
                    INDEX idx_timestamp (timestamp),
                    INDEX idx_status (status),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            ''')
            print("Scraping history table created successfully")
            
            conn.commit()
            print("Database initialization completed successfully!")
            
    except Error as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("Database connection closed")

if __name__ == "__main__":
    init_database() 