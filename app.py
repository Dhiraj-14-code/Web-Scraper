import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, make_response
import mysql.connector
from mysql.connector import pooling
from datetime import datetime
import json
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from flask_oauthlib.client import OAuth
from functools import wraps
from scraper import scrape_website

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Add debug logging for OAuth credentials
logger.info(f"GOOGLE_CLIENT_ID: {os.getenv('GOOGLE_CLIENT_ID', 'Not found')}")
logger.info(f"GOOGLE_CLIENT_SECRET: {os.getenv('GOOGLE_CLIENT_SECRET', 'Not found')}")

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))

# MySQL Configuration
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', 'mysql123'),
    'database': os.getenv('MYSQL_DATABASE', 'scraped_db'),
    'pool_name': 'mypool',
    'pool_size': 5
}

try:
    connection_pool = pooling.MySQLConnectionPool(**MYSQL_CONFIG)
    logger.info("MySQL connection pool created successfully")
except Exception as e:
    logger.error(f"Error creating MySQL connection pool: {e}")
    connection_pool = None

def get_db_connection():
    try:
        conn = connection_pool.get_connection()
        logger.info("Successfully connected to MySQL database")
        return conn
    except Exception as e:
        logger.error(f"Error connecting to MySQL database: {e}")
        return None

def init_db():
    logger.info("Attempting to initialize MySQL database...")
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            # Create users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_login DATETIME,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    is_oauth BOOLEAN NOT NULL DEFAULT FALSE,
                    oauth_provider VARCHAR(50),
                    oauth_id VARCHAR(255)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')
            logger.info("Users table created/verified successfully")
            # Create scraping history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scraping_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT,
                    url TEXT NOT NULL,
                    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    elements TEXT,
                    results LONGTEXT,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    execution_time FLOAT,
                    method VARCHAR(50),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')
            logger.info("Scraping history table created/verified successfully")
            conn.commit()
            logger.info("Database tables committed successfully")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
            logger.info("Database connection closed")
    else:
        logger.error("Failed to get database connection for initialization")

# Initialize database
init_db()

# OAuth Configuration
oauth = OAuth(app)

# Google OAuth Config
google = oauth.remote_app(
    'google',
    consumer_key=os.getenv('GOOGLE_CLIENT_ID'),
    consumer_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    request_token_params={
        'scope': 'email profile',
        'access_type': 'offline',
        'prompt': 'consent'  # Force consent screen to ensure refresh token
    },
    base_url='https://www.googleapis.com/oauth2/v1/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url='https://accounts.google.com/o/oauth2/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth'
)

# Log OAuth setup status
logger.info("OAuth configuration completed")

# Facebook OAuth Config
facebook = oauth.remote_app(
    'facebook',
    consumer_key=os.getenv('FACEBOOK_APP_ID', ''),
    consumer_secret=os.getenv('FACEBOOK_APP_SECRET', ''),
    request_token_params={'scope': 'email'},
    base_url='https://graph.facebook.com/',
    request_token_url=None,
    access_token_url='/oauth/access_token',
    access_token_method='GET',
    authorize_url='https://www.facebook.com/dialog/oauth'
)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/scrape', methods=['GET', 'POST'])
@login_required
def scrape():
    if request.method == 'GET':
        return render_template('scrape.html')
    
    start_time = datetime.now()
    try:
        data = request.get_json()
        url = data.get('url')
        elements = data.get('elements', [])
        method = data.get('method', 'auto')
        custom_selectors = data.get('customSelectors')
        custom_scraping_logic = data.get('customScrapingLogic')

        if not url:
            return jsonify({'error': 'URL is required', 'success': False}), 400

        result = scrape_website(url=url, method=method, elements=elements)
        execution_time = (datetime.now() - start_time).total_seconds()

        # Format the response to match what the frontend expects
        response_data = {
            'success': 'error' not in result,
            'data': result,
            'message': 'Successfully scraped the website',
            'execution_time': execution_time
        }

        # Save result to database
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor(dictionary=True)
                sql = '''INSERT INTO scraping_history 
                        (user_id, url, elements, results, status, error_message, execution_time, method)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)'''
                
                values = (
                    session['user_id'],  # Add user_id
                    url,
                    json.dumps(elements) if elements else None,
                    json.dumps(result, default=str) if result else None,
                    'success' if 'error' not in result else 'error',
                    result.get('error', None),
                    execution_time,
                    method
                )
                
                cursor.execute(sql, values)
                conn.commit()
                logger.info(f"Saved scraping result for user {session['user_id']}")
            except Exception as e:
                logger.error(f"Error saving to database: {e}")
                conn.rollback()
            finally:
                cursor.close()
                conn.close()

        return jsonify(response_data)
    
    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds()
        error_result = {
            'success': False,
            'error': str(e),
            'message': 'Failed to scrape the website'
        }

        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor(dictionary=True)
                sql = '''INSERT INTO scraping_history 
                        (user_id, url, elements, status, error_message, execution_time, method)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)'''
                
                values = (
                    session['user_id'],  # Add user_id
                    url if 'url' in locals() else 'Unknown',
                    json.dumps(elements) if 'elements' in locals() and elements else None,
                    'error',
                    str(e),
                    execution_time,
                    method if 'method' in locals() else 'auto'
                )
                
                cursor.execute(sql, values)
                conn.commit()
                logger.info(f"Saved error result for user {session['user_id']}")
            except Exception as e:
                logger.error(f"Error saving error to database: {e}")
                conn.rollback()
            finally:
                cursor.close()
                conn.close()

        return jsonify(error_result), 500

@app.route('/history')
@login_required
def history():
    conn = get_db_connection()
    history_items = []
    
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            # First, update any unassigned scraping history entries
            cursor.execute('''
                UPDATE scraping_history 
                SET user_id = %s 
                WHERE user_id IS NULL AND 
                      timestamp >= (SELECT created_at FROM users WHERE id = %s)
            ''', (session['user_id'], session['user_id']))
            conn.commit()
            
            # Then fetch history for this user only
            cursor.execute('''
                SELECT * FROM scraping_history 
                WHERE user_id = %s
                ORDER BY timestamp DESC
                LIMIT 100
            ''', (session['user_id'],))
            history_items = cursor.fetchall()
            
            logger.info(f"Retrieved {len(history_items)} history items for user {session['user_id']}")

            # Convert JSON fields to Python objects
            for item in history_items:
                item['elements'] = json.loads(item['elements']) if item['elements'] else []
                item['results'] = json.loads(item['results']) if item['results'] else {}

        except Exception as e:
            logger.error(f"Error fetching history: {e}")
        finally:
            cursor.close()
            conn.close()
    
    return render_template('history.html', history=history_items)

@app.route('/result/<int:id>')
@login_required
def result(id):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT * FROM scraping_history WHERE id = %s', (id,))
            history_item = cursor.fetchone()

            if not history_item:
                return "Result not found", 404

            return render_template('result.html',
                                   url=history_item['url'],
                                   elements=json.loads(history_item['elements']) if history_item['elements'] else [],
                                   results=json.loads(history_item['results']) if history_item['results'] else {},
                                   timestamp=history_item['timestamp'],
                                   status=history_item['status'],
                                   execution_time=history_item['execution_time'])
        except Exception as e:
            print(f"Error fetching result: {e}")
            return "Error fetching result", 500
        finally:
            cursor.close()
            conn.close()

    return "Database connection error", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    try:
        email = request.form.get('email')
        password = request.form.get('password')

        # Log login attempt
        logger.info(f"Login attempt - Email: {email}")

        # Input validation
        if not all([email, password]):
            logger.warning("Login failed: Missing email or password")
            flash('Email and password are required', 'error')
            return redirect(url_for('login'))

        # Database operations
        conn = get_db_connection()
        if not conn:
            logger.error("Failed to get database connection during login")
            flash('Database connection error', 'error')
            return redirect(url_for('login'))

        try:
            cursor = conn.cursor(dictionary=True)
            # Get user by email
            cursor.execute('SELECT id, username, email, password_hash, is_oauth FROM users WHERE email = %s', (email,))
            user = cursor.fetchone()

            if user and ('is_oauth' in user) and not user['is_oauth']:  # Only check password for non-OAuth users
                if check_password_hash(user['password_hash'], password):
                    # Update last login
                    cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s', (user['id'],))
                    conn.commit()

                    # Store user info in session
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['email'] = user['email']

                    logger.info(f"User logged in successfully: {email}")
                    flash('Successfully logged in!', 'success')
                    return redirect(url_for('home'))
                else:
                    logger.warning(f"Login failed: Invalid password for {email}")
            else:
                logger.warning(f"Login failed: No user found with email {email}")

            flash('Invalid email or password', 'error')
            return redirect(url_for('login'))

        except Exception as e:
            logger.error(f"Database error during login: {str(e)}")
            flash(f'An error occurred during login: {str(e)}', 'error')
            return redirect(url_for('login'))
        finally:
            cursor.close()
            conn.close()
            logger.info("Database connection closed")

    except Exception as e:
        logger.error(f"Unexpected error during login: {str(e)}", exc_info=True)
        flash(f'An unexpected error occurred: {str(e)}', 'error')
        return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    
    try:
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Log registration attempt
        logger.info(f"Registration attempt - Username: {username}, Email: {email}")

        # Input validation
        if not all([username, email, password, confirm_password]):
            missing_fields = [field for field in ['username', 'email', 'password', 'confirm_password'] 
                            if not request.form.get(field)]
            logger.warning(f"Registration failed: Missing fields - {', '.join(missing_fields)}")
            flash('All fields are required', 'error')
            return redirect(url_for('register'))

        if password != confirm_password:
            logger.warning("Registration failed: Passwords do not match")
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))

        if len(password) < 8:
            logger.warning("Registration failed: Password too short")
            flash('Password must be at least 8 characters long', 'error')
            return redirect(url_for('register'))

        if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            logger.warning("Registration failed: Password requirements not met")
            flash('Password must contain at least one letter and one number', 'error')
            return redirect(url_for('register'))

        # Database operations
        conn = get_db_connection()
        if not conn:
            logger.error("Failed to get database connection during registration")
            flash('Database connection error', 'error')
            return redirect(url_for('register'))

        try:
            cursor = conn.cursor(dictionary=True)
            # Check for existing user
            cursor.execute('SELECT id FROM users WHERE username = %s OR email = %s', (username, email))
            existing_user = cursor.fetchone()
            
            if existing_user:
                logger.warning(f"Registration failed: Username or email already exists - {username}, {email}")
                flash('Username or email already exists', 'error')
                return redirect(url_for('register'))

            # Create new user
            password_hash = generate_password_hash(password)
            cursor.execute(
                'INSERT INTO users (username, email, password_hash, created_at) VALUES (%s, %s, %s, CURRENT_TIMESTAMP)',
                (username, email, password_hash)
            )
            conn.commit()
            
            logger.info(f"User registered successfully: {username}")
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            conn.rollback()
            logger.error(f"Database error during registration: {str(e)}")
            flash('An error occurred during registration', 'error')
            return redirect(url_for('register'))
        finally:
            cursor.close()
            conn.close()
            logger.info("Database connection closed")

    except Exception as e:
        logger.error(f"Unexpected error during registration: {str(e)}", exc_info=True)
        flash('An unexpected error occurred', 'error')
        return redirect(url_for('register'))

@app.route('/test')
def test_page():
    return render_template('test_scrape.html')

@app.route('/docs')
def docs():
    return render_template('docs.html')

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

@app.route('/login/google')
def google_login():
    try:
        logger.info("Initiating Google OAuth login")
        return google.authorize(callback=url_for('google_authorized', _external=True))
    except Exception as e:
        logger.error(f"Error during Google OAuth login: {str(e)}")
        flash('Failed to initiate Google login. Please try again.', 'error')
        return redirect(url_for('login'))

@app.route('/login/google/authorized')
def google_authorized():
    try:
        logger.info("Handling Google OAuth callback")
        resp = google.authorized_response()
        
        if resp is None or resp.get('access_token') is None:
            logger.error(f"Access denied: reason={request.args.get('error_reason')} error={request.args.get('error_description')}")
            flash('Access denied: ' + request.args.get('error_description', 'Unknown error'), 'error')
            return redirect(url_for('login'))
        
        logger.info("Successfully obtained Google access token")
        session['google_token'] = (resp['access_token'], '')
        
        try:
            me = google.get('userinfo')
            logger.info(f"Retrieved user info for email: {me.data.get('email')}")
            
            # Check if user exists in database
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute('SELECT id FROM users WHERE email = %s', (me.data['email'],))
                    user = cursor.fetchone()
                    
                    if not user:
                        # Create new user
                        cursor.execute(
                            'INSERT INTO users (username, email, password_hash, is_oauth, oauth_provider) VALUES (%s, %s, %s, %s, %s)',
                            (me.data.get('name'), me.data['email'], 'oauth_user', True, 'google')
                        )
                        conn.commit()
                        logger.info(f"Created new user with Google OAuth: {me.data.get('email')}")
                    else:
                        logger.info(f"Existing user logged in with Google: {me.data.get('email')}")
                    
                    flash('Successfully logged in with Google!', 'success')
                    return redirect(url_for('home'))
                except Exception as e:
                    logger.error(f"Database error during Google OAuth: {str(e)}")
                    flash('An error occurred during login', 'error')
                finally:
                    cursor.close()
                    conn.close()
            
        except Exception as e:
            logger.error(f"Error getting user info from Google: {str(e)}")
            flash('Failed to get user info from Google', 'error')
            
    except Exception as e:
        logger.error(f"Error during Google OAuth callback: {str(e)}")
        flash('An error occurred during Google login', 'error')
    
    return redirect(url_for('login'))

@app.route('/login/facebook')
def facebook_login():
    return facebook.authorize(callback=url_for('facebook_authorized', _external=True))

@app.route('/login/facebook/authorized')
def facebook_authorized():
    resp = facebook.authorized_response()
    if resp is None or resp.get('access_token') is None:
        return 'Access denied: reason={} error={}'.format(
            request.args['error_reason'],
            request.args['error_description']
        )
    
    session['facebook_token'] = (resp['access_token'], '')
    me = facebook.get('/me?fields=id,name,email')
    
    # Check if user exists in database
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT id FROM users WHERE email = %s', (me.data['email'],))
            user = cursor.fetchone()
            
            if not user:
                # Create new user
                cursor.execute(
                    'INSERT INTO users (username, email, password_hash, is_oauth) VALUES (%s, %s, %s, %s)',
                    (me.data.get('name'), me.data['email'], 'oauth_user', True)
                )
                conn.commit()
                
            flash('Successfully logged in with Facebook!', 'success')
            return redirect(url_for('home'))
        except Exception as e:
            logger.error(f"Database error during Facebook OAuth: {str(e)}")
            flash('An error occurred during login', 'error')
        finally:
            cursor.close()
            conn.close()
    
    return redirect(url_for('login'))

@google.tokengetter
def get_google_oauth_token():
    return session.get('google_token')

@facebook.tokengetter
def get_facebook_oauth_token():
    return session.get('facebook_token')

@app.teardown_appcontext
def close_connection(exception):
    """Ensure database connections are closed after requests"""
    conn = get_db_connection()
    if conn:
        conn.close()

@app.route('/logout')
def logout():
    # Clear all session data
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

@app.route('/profile')
@login_required
def profile():
    try:
        logger.info(f"Accessing profile for user_id: {session.get('user_id')}")
        conn = get_db_connection()
        if not conn:
            logger.error("Database connection failed in profile route")
            flash('Database connection error', 'error')
            return redirect(url_for('home'))

        user_data = None
        scraping_stats = None
        recent_activities = []

        try:
            cursor = conn.cursor(dictionary=True)
            # Get user information
            cursor.execute('''
                SELECT id, username, email, created_at, last_login, is_oauth, oauth_provider 
                FROM users WHERE id = %s
            ''', (session['user_id'],))
            user_data = cursor.fetchone()
            print("USER DATA:", user_data)
            print("SESSION USER_ID:", session.get('user_id'))

            if not user_data:
                logger.error(f"No user found for id: {session.get('user_id')}")
                flash('User not found', 'error')
                return redirect(url_for('home'))

            # Update scraping history entries that don't have user_id
            cursor.execute('''
                UPDATE scraping_history 
                SET user_id = %s 
                WHERE user_id IS NULL AND 
                      timestamp >= (SELECT created_at FROM users WHERE id = %s)
            ''', (session['user_id'], session['user_id']))
            conn.commit()

            # Get scraping statistics
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_scrapes,
                    COUNT(CASE WHEN status = 'success' THEN 1 END) as successful_scrapes,
                    COUNT(CASE WHEN status = 'error' THEN 1 END) as failed_scrapes,
                    AVG(CASE WHEN execution_time IS NOT NULL THEN execution_time ELSE 0 END) as avg_execution_time,
                    MAX(timestamp) as last_scrape_time,
                    MIN(timestamp) as first_scrape_time,
                    SUM(CASE WHEN execution_time IS NOT NULL THEN execution_time ELSE 0 END) as total_execution_time
                FROM scraping_history 
                WHERE user_id = %s
            ''', (session['user_id'],))
            scraping_stats = cursor.fetchone()

            # Get recent activities
            cursor.execute('''
                SELECT id, url, timestamp, status, execution_time, error_message
                FROM scraping_history 
                WHERE user_id = %s
                ORDER BY timestamp DESC 
                LIMIT 5
            ''', (session['user_id'],))
            recent_activities = cursor.fetchall() or []

        except Exception as e:
            logger.error(f"Database error in profile route: {str(e)}")
            flash('Error fetching profile data', 'error')
            return redirect(url_for('home'))
        finally:
            cursor.close()
            conn.close()

        # Set default values if stats are None
        if scraping_stats:
            scraping_stats = {
                'total_scrapes': scraping_stats['total_scrapes'] or 0,
                'successful_scrapes': scraping_stats['successful_scrapes'] or 0,
                'failed_scrapes': scraping_stats['failed_scrapes'] or 0,
                'avg_execution_time': scraping_stats['avg_execution_time'] or 0,
                'last_scrape_time': scraping_stats['last_scrape_time'],
                'first_scrape_time': scraping_stats['first_scrape_time'],
                'total_execution_time': scraping_stats['total_execution_time'] or 0
            }
        else:
            scraping_stats = {
                'total_scrapes': 0,
                'successful_scrapes': 0,
                'failed_scrapes': 0,
                'avg_execution_time': 0,
                'last_scrape_time': None,
                'first_scrape_time': None,
                'total_execution_time': 0
            }

        print("SCRAPING STATS:", scraping_stats)
        print("RECENT ACTIVITIES:", recent_activities)

        return render_template('profile.html', 
                            user=user_data, 
                            stats=scraping_stats, 
                            recent_activities=recent_activities or [])

    except Exception as e:
        logger.error(f"Unexpected error in profile route: {str(e)}", exc_info=True)
        flash('An unexpected error occurred', 'error')
        return redirect(url_for('home'))

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'GET':
        return render_template('change_password.html')
    
    try:
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not all([current_password, new_password, confirm_password]):
            flash('All fields are required', 'error')
            return redirect(url_for('change_password'))

        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('change_password'))

        if len(new_password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return redirect(url_for('change_password'))

        conn = get_db_connection()
        if not conn:
            flash('Database connection error', 'error')
            return redirect(url_for('change_password'))

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT password_hash FROM users WHERE id = %s', (session['user_id'],))
            user = cursor.fetchone()

            if not check_password_hash(user['password_hash'], current_password):
                flash('Current password is incorrect', 'error')
                return redirect(url_for('change_password'))

            new_password_hash = generate_password_hash(new_password)
            cursor.execute('UPDATE users SET password_hash = %s WHERE id = %s',
                         (new_password_hash, session['user_id']))
            conn.commit()

            flash('Password successfully updated', 'success')
            return redirect(url_for('profile'))

        except Exception as e:
            logger.error(f"Database error during password change: {str(e)}")
            flash('An error occurred while changing password', 'error')
            return redirect(url_for('change_password'))
        finally:
            cursor.close()
            conn.close()

    except Exception as e:
        logger.error(f"Unexpected error during password change: {str(e)}")
        flash('An unexpected error occurred', 'error')
        return redirect(url_for('change_password'))

@app.route('/export-data')
@login_required
def export_data():
    try:
        conn = get_db_connection()
        if not conn:
            flash('Database connection error', 'error')
            return redirect(url_for('profile'))

        try:
            cursor = conn.cursor(dictionary=True)
            # Get user data
            cursor.execute('''
                SELECT username, email, created_at, last_login, is_oauth, oauth_provider
                FROM users WHERE id = %s
            ''', (session['user_id'],))
            user_data = cursor.fetchone()

            # Get all scraping history
            cursor.execute('''
                SELECT url, timestamp, status, execution_time, error_message, results
                FROM scraping_history 
                WHERE user_id = %s
                ORDER BY timestamp DESC
            ''', (session['user_id'],))
            scraping_history = cursor.fetchall()

            # Prepare export data
            export_data = {
                'user_info': user_data,
                'scraping_history': scraping_history
            }

            # Convert to JSON
            json_data = json.dumps(export_data, default=str, indent=2)
            
            # Create response
            response = make_response(json_data)
            response.headers['Content-Type'] = 'application/json'
            response.headers['Content-Disposition'] = f'attachment; filename=web_scraper_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            
            return response

        except Exception as e:
            logger.error(f"Database error during data export: {str(e)}")
            flash('An error occurred while exporting data', 'error')
            return redirect(url_for('profile'))
        finally:
            cursor.close()
            conn.close()

    except Exception as e:
        logger.error(f"Unexpected error during data export: {str(e)}")
        flash('An unexpected error occurred', 'error')
        return redirect(url_for('profile'))

@app.route('/delete-account', methods=['GET', 'POST'])
@login_required
def delete_account():
    if request.method == 'GET':
        return render_template('delete_account.html')
    
    try:
        password = request.form.get('password')
        confirm = request.form.get('confirm')

        if not password or confirm != "DELETE":
            flash('Please provide your password and type DELETE to confirm', 'error')
            return redirect(url_for('delete_account'))

        conn = get_db_connection()
        if not conn:
            flash('Database connection error', 'error')
            return redirect(url_for('delete_account'))

        try:
            cursor = conn.cursor(dictionary=True)
            # Verify password for non-OAuth users
            if not session.get('is_oauth'):
                cursor.execute('SELECT password_hash FROM users WHERE id = %s', (session['user_id'],))
                user = cursor.fetchone()

                if not check_password_hash(user['password_hash'], password):
                    flash('Incorrect password', 'error')
                    return redirect(url_for('delete_account'))

            # Delete user's scraping history
            cursor.execute('DELETE FROM scraping_history WHERE user_id = %s', (session['user_id'],))
            
            # Delete user
            cursor.execute('DELETE FROM users WHERE id = %s', (session['user_id'],))
            conn.commit()

            # Clear session
            session.clear()
            flash('Your account has been successfully deleted', 'success')
            return redirect(url_for('home'))

        except Exception as e:
            logger.error(f"Database error during account deletion: {str(e)}")
            flash('An error occurred while deleting account', 'error')
            return redirect(url_for('delete_account'))
        finally:
            cursor.close()
            conn.close()

    except Exception as e:
        logger.error(f"Unexpected error during account deletion: {str(e)}")
        flash('An unexpected error occurred', 'error')
        return redirect(url_for('delete_account'))

@app.route('/test-db')
def test_db():
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT 1")
            cursor.close()
            conn.close()
            return "Database connection successful!"
        else:
            return "Failed to connect to the database.", 500
    except Exception as e:
        return f"Database connection error: {e}", 500

if __name__ == '__main__':
    app.run(debug=True)
