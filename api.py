from flask import Blueprint, request, jsonify, current_app
import json
from scraper import scrape_website
from datetime import datetime
import mysql.connector
from mysql.connector import Error
from functools import wraps
import os
import logging
import re
from werkzeug.security import check_password_hash
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create API blueprint
api = Blueprint('api', __name__)

# Global rate limiting
API_RATE_LIMITS = {
    'default': {'calls': 100, 'period': 3600},  # 100 calls per hour
    'premium': {'calls': 1000, 'period': 3600}  # 1000 calls per hour
}

# Global rate limit tracking
user_rate_limits = {}

# Active tasks
active_tasks = {}

def get_db_connection():
    """Get a database connection"""
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', 'mysql123'),
            database=os.getenv('DB_NAME', 'scraped_db'),
            auth_plugin='mysql_native_password'
        )
        return conn
    except Error as e:
        logger.error(f"Error connecting to MySQL: {e}")
        return None

def api_key_required(f):
    """Decorator to require API key authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({'error': 'API key is required'}), 401
        
        # Verify API key
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection error'}), 500
        
        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(
                    "SELECT * FROM api_keys WHERE api_key = %s AND active = TRUE",
                    (api_key,)
                )
                key_info = cursor.fetchone()
                
                if not key_info:
                    return jsonify({'error': 'Invalid API key'}), 401
                
                # Get user info
                cursor.execute(
                    "SELECT id, username, email FROM users WHERE id = %s",
                    (key_info['user_id'],)
                )
                user_info = cursor.fetchone()
                
                if not user_info:
                    return jsonify({'error': 'User not found'}), 401
                
                # Check rate limit
                if not check_rate_limit(key_info['user_id'], key_info['tier']):
                    return jsonify({'error': 'Rate limit exceeded'}), 429
                
                # Update last used timestamp
                cursor.execute(
                    "UPDATE api_keys SET last_used = NOW(), call_count = call_count + 1 WHERE api_key = %s",
                    (api_key,)
                )
                conn.commit()
                
                # Store user info for the view function
                request.user_id = user_info['id']
                request.username = user_info['username']
                request.email = user_info['email']
                request.api_tier = key_info['tier']
                
                return f(*args, **kwargs)
                
        except Error as e:
            logger.error(f"Database error during API authentication: {e}")
            return jsonify({'error': 'Authentication failed'}), 500
        finally:
            conn.close()
            
    return decorated_function

def check_rate_limit(user_id, tier):
    """Check if user has exceeded their rate limit"""
    current_time = time.time()
    
    # Get rate limit for tier
    rate_limit = API_RATE_LIMITS.get(tier, API_RATE_LIMITS['default'])
    period = rate_limit['period']
    max_calls = rate_limit['calls']
    
    # Initialize user's rate limit tracking if not exists
    if user_id not in user_rate_limits:
        user_rate_limits[user_id] = {'calls': [], 'tier': tier}
    
    # Update tracking info for user
    calls = user_rate_limits[user_id]['calls']
    
    # Remove expired timestamps
    calls = [ts for ts in calls if current_time - ts < period]
    
    # Check if limit exceeded
    if len(calls) >= max_calls:
        return False
    
    # Add current timestamp and update
    calls.append(current_time)
    user_rate_limits[user_id]['calls'] = calls
    
    return True

def sanitize_url(url):
    """Sanitize and validate URL"""
    if not url or not isinstance(url, str):
        return None
    
    # Ensure URL has proper scheme
    if not re.match(r'^https?://', url):
        url = 'http://' + url
    
    # Basic validation
    if not re.match(r'^https?://[\w\-\.]+\.\w+', url):
        return None
    
    return url

@api.route('/scrape', methods=['POST'])
@api_key_required
def api_scrape():
    """API endpoint for scraping a website"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        url = sanitize_url(data.get('url'))
        if not url:
            return jsonify({'error': 'Invalid or missing URL'}), 400
        
        # Extract parameters
        method = data.get('method', 'auto')
        elements = data.get('elements')
        custom_selectors = data.get('custom_selectors')
        export_format = data.get('export_format')
        async_mode = data.get('async', False)
        
        # Validate method
        if method not in ['auto', 'static', 'dynamic']:
            return jsonify({'error': 'Invalid scraping method. Use auto, static, or dynamic'}), 400
        
        # For async scraping
        if async_mode:
            task_id = str(uuid.uuid4())
            task = {
                'id': task_id,
                'status': 'pending',
                'user_id': request.user_id,
                'url': url,
                'created_at': datetime.now(),
                'result': None
            }
            active_tasks[task_id] = task
            
            # Start background thread
            threading.Thread(
                target=run_scrape_task,
                args=(task_id, url, method, elements, custom_selectors, export_format)
            ).start()
            
            return jsonify({
                'task_id': task_id,
                'status': 'pending',
                'message': 'Scraping started in the background'
            })
        
        # For synchronous scraping
        start_time = datetime.now()
        result = scrape_website(
            url=url,
            method=method,
            elements=elements,
            custom_selectors=custom_selectors,
            export_format=export_format
        )
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # Save to database
        save_scrape_result(request.user_id, url, method, elements, result, execution_time)
        
        # Return result
        return jsonify({
            'success': 'error' not in result,
            'data': result,
            'execution_time': execution_time
        })
        
    except Exception as e:
        logger.error(f"API scraping error: {str(e)}")
        return jsonify({'error': str(e)}), 500

def run_scrape_task(task_id, url, method, elements, custom_selectors, export_format):
    """Run a scraping task asynchronously"""
    try:
        # Update task status
        active_tasks[task_id]['status'] = 'running'
        
        # Run scraping
        start_time = datetime.now()
        result = scrape_website(
            url=url,
            method=method,
            elements=elements,
            custom_selectors=custom_selectors,
            export_format=export_format
        )
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # Save to database
        save_scrape_result(
            active_tasks[task_id]['user_id'],
            url,
            method,
            elements,
            result,
            execution_time
        )
        
        # Update task with result
        active_tasks[task_id]['status'] = 'completed'
        active_tasks[task_id]['result'] = result
        active_tasks[task_id]['completed_at'] = datetime.now()
        active_tasks[task_id]['execution_time'] = execution_time
        
    except Exception as e:
        logger.error(f"Error in background scraping task: {str(e)}")
        active_tasks[task_id]['status'] = 'error'
        active_tasks[task_id]['error'] = str(e)

def save_scrape_result(user_id, url, method, elements, result, execution_time):
    """Save the scraping result to the database"""
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database to save scraping result")
        return
    
    try:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO scraping_history 
                (user_id, url, elements, results, status, error_message, execution_time, method)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                user_id,
                url,
                json.dumps(elements) if elements else None,
                json.dumps(result, default=str) if result else None,
                'success' if 'error' not in result else 'error',
                result.get('error', None),
                execution_time,
                method
            ))
            conn.commit()
            logger.info(f"Saved API scraping result for user {user_id}")
    except Error as e:
        logger.error(f"Error saving to database: {e}")
    finally:
        conn.close()

@api.route('/task/<task_id>', methods=['GET'])
@api_key_required
def get_task_status(task_id):
    """Get status of an asynchronous scraping task"""
    if task_id not in active_tasks:
        return jsonify({'error': 'Task not found'}), 404
    
    task = active_tasks[task_id]
    
    # Check if user owns this task
    if task['user_id'] != request.user_id:
        return jsonify({'error': 'Unauthorized access to task'}), 403
    
    response = {
        'task_id': task_id,
        'status': task['status'],
        'created_at': task['created_at'].isoformat()
    }
    
    # Add result if completed
    if task['status'] == 'completed':
        response['result'] = task['result']
        response['execution_time'] = task['execution_time']
        response['completed_at'] = task['completed_at'].isoformat()
    
    # Add error if failed
    if task['status'] == 'error':
        response['error'] = task['error']
    
    return jsonify(response)

@api.route('/history', methods=['GET'])
@api_key_required
def get_history():
    """Get scraping history for the authenticated user"""
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    # Sanitize limit and offset
    limit = min(limit, 100)  # Max 100 items per request
    limit = max(limit, 1)    # Min 1 item
    offset = max(offset, 0)  # Min offset 0
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection error'}), 500
    
    try:
        with conn.cursor(dictionary=True) as cursor:
            # Get total count
            cursor.execute(
                "SELECT COUNT(*) as count FROM scraping_history WHERE user_id = %s",
                (request.user_id,)
            )
            total = cursor.fetchone()['count']
            
            # Get history items
            cursor.execute('''
                SELECT id, url, timestamp, elements, status, error_message, execution_time, method
                FROM scraping_history 
                WHERE user_id = %s
                ORDER BY timestamp DESC
                LIMIT %s OFFSET %s
            ''', (request.user_id, limit, offset))
            
            history = cursor.fetchall()
            
            # Process JSON fields
            for item in history:
                item['elements'] = json.loads(item['elements']) if item['elements'] else None
                item['timestamp'] = item['timestamp'].isoformat()
            
            return jsonify({
                'total': total,
                'limit': limit,
                'offset': offset,
                'history': history
            })
            
    except Error as e:
        logger.error(f"Database error retrieving history: {e}")
        return jsonify({'error': 'Failed to retrieve history'}), 500
    finally:
        conn.close()

@api.route('/generate-key', methods=['POST'])
def generate_api_key():
    """Generate a new API key for a user"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Verify user credentials
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection error'}), 500
        
        try:
            with conn.cursor(dictionary=True) as cursor:
                # Check user credentials
                cursor.execute(
                    "SELECT id, password_hash FROM users WHERE username = %s",
                    (username,)
                )
                user = cursor.fetchone()
                
                if not user or not check_password_hash(user['password_hash'], password):
                    return jsonify({'error': 'Invalid credentials'}), 401
                
                # Generate API key
                api_key = str(uuid.uuid4())
                
                # Store API key
                cursor.execute('''
                    INSERT INTO api_keys
                    (user_id, api_key, tier, created_at, active)
                    VALUES (%s, %s, %s, NOW(), TRUE)
                ''', (
                    user['id'],
                    api_key,
                    'default'  # Default tier
                ))
                conn.commit()
                
                return jsonify({
                    'api_key': api_key,
                    'message': 'API key generated successfully. Keep this key secure.'
                })
                
        except Error as e:
            logger.error(f"Database error generating API key: {e}")
            return jsonify({'error': 'Failed to generate API key'}), 500
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error generating API key: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api.route('/multi-scrape', methods=['POST'])
@api_key_required
def multi_scrape():
    """Scrape multiple URLs in parallel"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        urls = data.get('urls', [])
        if not urls or not isinstance(urls, list) or len(urls) == 0:
            return jsonify({'error': 'URLs must be a non-empty list'}), 400
        
        # Limit number of URLs based on tier
        max_urls = 10 if request.api_tier == 'default' else 50
        if len(urls) > max_urls:
            return jsonify({'error': f'Maximum {max_urls} URLs allowed for your tier'}), 400
        
        # Sanitize URLs
        sanitized_urls = [sanitize_url(url) for url in urls]
        sanitized_urls = [url for url in sanitized_urls if url]
        
        if not sanitized_urls:
            return jsonify({'error': 'No valid URLs provided'}), 400
        
        # Extract parameters
        method = data.get('method', 'auto')
        elements = data.get('elements')
        custom_selectors = data.get('custom_selectors')
        async_mode = data.get('async', False)
        
        # For async scraping
        if async_mode:
            task_id = str(uuid.uuid4())
            task = {
                'id': task_id,
                'status': 'pending',
                'user_id': request.user_id,
                'urls': sanitized_urls,
                'created_at': datetime.now(),
                'results': None,
                'completed_urls': 0,
                'total_urls': len(sanitized_urls)
            }
            active_tasks[task_id] = task
            
            # Start background thread
            threading.Thread(
                target=run_multi_scrape_task,
                args=(task_id, sanitized_urls, method, elements, custom_selectors)
            ).start()
            
            return jsonify({
                'task_id': task_id,
                'status': 'pending',
                'message': f'Scraping of {len(sanitized_urls)} URLs started in the background'
            })
        
        # For synchronous scraping
        start_time = datetime.now()
        results = {}
        
        # Use ThreadPoolExecutor for parallel scraping
        with ThreadPoolExecutor(max_workers=min(len(sanitized_urls), 5)) as executor:
            future_to_url = {
                executor.submit(
                    scrape_website,
                    url=url,
                    method=method,
                    elements=elements,
                    custom_selectors=custom_selectors
                ): url for url in sanitized_urls
            }
            
            for future in future_to_url:
                url = future_to_url[future]
                try:
                    result = future.result()
                    results[url] = result
                    
                    # Save to database
                    execution_time = (datetime.now() - start_time).total_seconds()
                    save_scrape_result(
                        request.user_id,
                        url,
                        method,
                        elements,
                        result,
                        execution_time
                    )
                except Exception as e:
                    results[url] = {'error': str(e)}
        
        total_time = (datetime.now() - start_time).total_seconds()
        
        return jsonify({
            'success': True,
            'data': results,
            'total_execution_time': total_time
        })
        
    except Exception as e:
        logger.error(f"API multi-scraping error: {str(e)}")
        return jsonify({'error': str(e)}), 500

def run_multi_scrape_task(task_id, urls, method, elements, custom_selectors):
    """Run multiple scraping tasks asynchronously"""
    try:
        # Update task status
        active_tasks[task_id]['status'] = 'running'
        active_tasks[task_id]['results'] = {}
        
        # Start time for the entire batch
        start_time = datetime.now()
        
        # Use ThreadPoolExecutor for parallel scraping
        with ThreadPoolExecutor(max_workers=min(len(urls), 5)) as executor:
            future_to_url = {
                executor.submit(
                    scrape_website,
                    url=url,
                    method=method,
                    elements=elements,
                    custom_selectors=custom_selectors
                ): url for url in urls
            }
            
            for future in future_to_url:
                url = future_to_url[future]
                try:
                    result = future.result()
                    active_tasks[task_id]['results'][url] = result
                    
                    # Save to database
                    execution_time = (datetime.now() - start_time).total_seconds()
                    save_scrape_result(
                        active_tasks[task_id]['user_id'],
                        url,
                        method,
                        elements,
                        result,
                        execution_time
                    )
                except Exception as e:
                    active_tasks[task_id]['results'][url] = {'error': str(e)}
                
                # Update progress
                active_tasks[task_id]['completed_urls'] += 1
        
        # Update task with completion info
        active_tasks[task_id]['status'] = 'completed'
        active_tasks[task_id]['completed_at'] = datetime.now()
        active_tasks[task_id]['execution_time'] = (datetime.now() - start_time).total_seconds()
        
    except Exception as e:
        logger.error(f"Error in background multi-scraping task: {str(e)}")
        active_tasks[task_id]['status'] = 'error'
        active_tasks[task_id]['error'] = str(e) 