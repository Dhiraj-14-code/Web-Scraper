import schedule
import time
import threading
import json
import os
import logging
from datetime import datetime, timedelta
from scraper import scrape_website
import mysql.connector
from typing import Dict, List, Any, Optional, Union
from mysql.connector import Error
from config import DB_CONFIG, EMAIL_CONFIG
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app import get_db_connection

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ScraperScheduler:
    def __init__(self):
        self.running = False
        self.scheduler_thread = None
        self.jobs = {}  # job_id: schedule.Job

    def get_db_connection(self):
        """Create a connection to the MySQL database."""
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            return conn
        except Error as e:
            logger.error(f"Error connecting to MySQL database: {e}")
            return None

    def load_jobs(self):
        """Load all active jobs from the database."""
        conn = self.get_db_connection()
        if not conn:
            return

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM scheduled_jobs WHERE status = 'active'"
            )
            jobs = cursor.fetchall()
            logger.info(f"Loaded {len(jobs)} jobs from the database")
            
            # Clear current schedule
            schedule.clear()
            self.jobs = {}
            
            # Schedule each job
            for job in jobs:
                self.schedule_job(job)
                
        except Error as e:
            logger.error(f"Error loading jobs: {e}")
        finally:
            cursor.close()
            conn.close()

    def schedule_job(self, job):
        """Schedule a job based on its frequency."""
        job_id = job['id']
        url = job['url']
        frequency = job['frequency']
        job_time = job['time']
        try:
            # Parse time
            hour, minute = map(int, job_time.split(':'))
            time_str = f"{hour:02d}:{minute:02d}"
            
            # Create the job function
            def job_func():
                self.execute_job(job_id)
            
            # Schedule based on frequency
            if frequency == 'hourly':
                scheduled_job = schedule.every().hour.at(f":{minute:02d}").do(job_func)
            elif frequency == 'daily':
                scheduled_job = schedule.every().day.at(time_str).do(job_func)
            elif frequency == 'weekly':
                day_index = int(job.get('day_of_week', 0))
                days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                day_method = getattr(schedule.every(), days[day_index])
                scheduled_job = day_method.at(time_str).do(job_func)
            elif frequency == 'monthly':
                day = job.get('day_of_month', 1)
                
                # For monthly jobs, we need to use a custom tag and check in the run_pending method
                scheduled_job = schedule.every().day.at(time_str).do(job_func)
                scheduled_job.tag(f"monthly_{job_id}_{day}")
            else:
                logger.error(f"Unknown frequency: {frequency} for job {job_id}")
                return
            
            # Store the job
            self.jobs[job_id] = scheduled_job
            logger.info(f"Scheduled job {job_id} ({url}) to run {frequency} at {time_str}")
            
            # Update next run time in database
            self.update_job_next_run(job_id)
            
        except Exception as e:
            logger.error(f"Error scheduling job {job_id}: {e}")

    def execute_job(self, job_id):
        """Execute a job by its ID."""
        conn = self.get_db_connection()
        if not conn:
            return

        cursor = conn.cursor(dictionary=True)
        try:
            # Get job details
            cursor.execute("SELECT * FROM scheduled_jobs WHERE id = %s", (job_id,))
            job = cursor.fetchone()
            
            if not job:
                logger.error(f"Job {job_id} not found")
                return
            
            logger.info(f"Executing job {job_id} ({job['url']})")
            
            # Execute the scraping task
            url = job['url']
            scrape_type = job['scrape_type']
            export_format = job['export_format']
            
            # Track execution start time
            start_time = datetime.now()
            
            # Execute scraping
            try:
                result = scrape_website(
                    url=url, 
                    method=scrape_type,
                    timeout=60,
                    follow_links=False
                )
                
                # Calculate execution time
                execution_time = (datetime.now() - start_time).total_seconds()
                
                # Save result to database
                cursor.execute(
                    """
                    INSERT INTO scrape_results 
                    (user_id, url, method, result, execution_time, created_at) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        job['user_id'],
                        url,
                        scrape_type,
                        json.dumps(result),
                        execution_time,
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    )
                )
                conn.commit()
                result_id = cursor.lastrowid
                
                # Record execution
                cursor.execute(
                    """
                    INSERT INTO job_executions
                    (job_id, execution_time, status, result_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        job_id,
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'success',
                        result_id
                    )
                )
                
                # Update job last run
                cursor.execute(
                    """
                    UPDATE scheduled_jobs 
                    SET last_run = %s, modified_at = %s
                    WHERE id = %s
                    """,
                    (
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        job_id
                    )
                )
                conn.commit()
                
                # Send email notification if enabled
                if job.get('email_notification'):
                    self.send_email_notification(job, 'success', result_id)
                
                logger.info(f"Job {job_id} executed successfully")
                
            except Exception as e:
                logger.error(f"Error executing job {job_id}: {e}")
                
                # Record failed execution
                cursor.execute(
                    """
                    INSERT INTO job_executions
                    (job_id, execution_time, status, error_message)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        job_id,
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'failed',
                        str(e)
                    )
                )
                
                # Update job last run
                cursor.execute(
                    """
                    UPDATE scheduled_jobs 
                    SET last_run = %s, modified_at = %s
                    WHERE id = %s
                    """,
                    (
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        job_id
                    )
                )
                conn.commit()
                
                # Send email notification for failure
                if job.get('email_notification'):
                    self.send_email_notification(job, 'failed', None, str(e))
            
            # Update next run time
            self.update_job_next_run(job_id)
            
        except Error as e:
            logger.error(f"Database error during job execution {job_id}: {e}")
        finally:
            cursor.close()
            conn.close()

    def update_job_next_run(self, job_id):
        """Update the next run time for a job in the database."""
        conn = self.get_db_connection()
        if not conn:
            return

        cursor = conn.cursor(dictionary=True)
        try:
            # Get job details
            cursor.execute("SELECT * FROM scheduled_jobs WHERE id = %s", (job_id,))
            job = cursor.fetchone()
            
            if not job or job_id not in self.jobs:
                return
            
            # Get next run time from schedule
            scheduled_job = self.jobs[job_id]
            next_run = scheduled_job.next_run
            
            # Update in database
            cursor.execute(
                "UPDATE scheduled_jobs SET next_run = %s, modified_at = %s WHERE id = %s",
                (
                    next_run.strftime('%Y-%m-%d %H:%M:%S') if next_run else None,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    job_id
                )
            )
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error updating next run time for job {job_id}: {e}")
        finally:
            cursor.close()
            conn.close()

    def send_email_notification(self, job, status, result_id=None, error_message=None):
        """Send email notification for job execution."""
        if not EMAIL_CONFIG.get('SMTP_SERVER') or not EMAIL_CONFIG.get('SENDER_EMAIL'):
            logger.warning("Email configuration missing. Skipping notification.")
            return
        
        try:
            # Get user email
            conn = self.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT email FROM users WHERE id = %s", (job['user_id'],))
            user = cursor.fetchone()
            
            if not user or not user.get('email'):
                logger.warning(f"No email found for user {job['user_id']}. Skipping notification.")
                return
            
            recipient_email = user['email']
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = EMAIL_CONFIG['SENDER_EMAIL']
            msg['To'] = recipient_email
            
            if status == 'success':
                msg['Subject'] = f"Web Scraper: Job '{job['url']}' completed successfully"
                body = f"""
                Your scheduled scraping job has completed successfully.
                
                URL: {job['url']}
                Execution time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                Frequency: {job['frequency']}
                
                You can view the results in your Web Scraper account.
                """
            else:
                msg['Subject'] = f"Web Scraper: Job '{job['url']}' failed"
                body = f"""
                Your scheduled scraping job has failed.
                
                URL: {job['url']}
                Execution time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                Frequency: {job['frequency']}
                
                Error: {error_message}
                
                Please check your Web Scraper account for more details.
                """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            with smtplib.SMTP(EMAIL_CONFIG['SMTP_SERVER'], EMAIL_CONFIG.get('SMTP_PORT', 587)) as server:
                if EMAIL_CONFIG.get('USE_TLS', True):
                    server.starttls()
                if EMAIL_CONFIG.get('SMTP_USERNAME') and EMAIL_CONFIG.get('SMTP_PASSWORD'):
                    server.login(EMAIL_CONFIG['SMTP_USERNAME'], EMAIL_CONFIG['SMTP_PASSWORD'])
                server.send_message(msg)
                
            logger.info(f"Email notification sent to {recipient_email} for job {job['id']}")
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
        finally:
            if conn:
                cursor.close()
                conn.close()

    def run(self):
        """Run the scheduler in a separate thread."""
        if self.running:
            logger.warning("Scheduler is already running")
            return

        def run_scheduler():
            self.running = True
            self.load_jobs()
            
            logger.info("Scheduler started")
            while self.running:
                try:
                    # Run pending jobs
                    schedule.run_pending()
                    
                    # Check for newly added or modified jobs every minute
                    if datetime.now().second == 0:
                        self.check_for_job_changes()
                    
                    # Sleep for a second
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"Error in scheduler loop: {e}")
                    time.sleep(5)  # Wait a bit longer on error
            
            logger.info("Scheduler stopped")

        self.scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()

    def check_for_job_changes(self):
        """Check for job additions, modifications, or deletions."""
        conn = self.get_db_connection()
        if not conn:
            return

        cursor = conn.cursor(dictionary=True)
        try:
            # Get all active jobs
            cursor.execute(
                "SELECT id, modified_at FROM scheduled_jobs WHERE status = 'active'"
            )
            current_jobs = {row['id']: row for row in cursor.fetchall()}
            
            # Check for new or modified jobs
            for job_id, job_data in current_jobs.items():
                if job_id not in self.jobs:
                    # New job
                    cursor.execute("SELECT * FROM scheduled_jobs WHERE id = %s", (job_id,))
                    job = cursor.fetchone()
                    self.schedule_job(job)
            
            # Check for deleted or paused jobs
            for job_id in list(self.jobs.keys()):
                if job_id not in current_jobs:
                    # Job deleted or paused
                    if job_id in self.jobs:
                        schedule.cancel_job(self.jobs[job_id])
                        del self.jobs[job_id]
                        logger.info(f"Removed job {job_id} from scheduler")
            
        except Error as e:
            logger.error(f"Error checking for job changes: {e}")
        finally:
            cursor.close()
            conn.close()

    def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
            self.scheduler_thread = None
        logger.info("Scheduler stopped")


# Initialize scheduler
scheduler = ScraperScheduler()

# Function to start the scheduler from the main app
def start_scheduler():
    scheduler.run()

# Main entry point for running as a standalone process
if __name__ == '__main__':
    try:
        scheduler.run()
        # Keep the main thread alive
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
        scheduler.stop()

def run_scheduled_job(job):
    """Execute a scheduled scraping job"""
    try:
        logger.info(f"Running scheduled job {job['id']} for URL: {job['url']}")
        
        # Prepare scraping parameters
        elements = ['text', 'links', 'images', 'tables']  # Default elements
        options = {
            'timeout': 30,
            'follow_links': False
        }
        
        # Execute the scraping
        result = scrape_website(
            url=job['url'],
            method=job['scrape_type'],
            elements=elements,
            options=options
        )
        
        # Save result to database
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                sql = '''INSERT INTO scraping_history 
                        (user_id, url, elements, results, status, error_message, execution_time, method)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''
                
                values = (
                    job['user_id'],
                    job['url'],
                    json.dumps(elements),
                    json.dumps(result, default=str),
                    'success' if 'error' not in result else 'error',
                    result.get('error', None),
                    0,  # execution_time will be updated
                    job['scrape_type']
                )
                
                cursor.execute(sql, values)
                conn.commit()
                logger.info(f"Saved result for scheduled job {job['id']}")
            except Exception as e:
                logger.error(f"Error saving scheduled job result: {e}")
            finally:
                conn.close()
        
    except Exception as e:
        logger.error(f"Error running scheduled job {job['id']}: {e}")

def check_scheduled_jobs():
    """Check and run any scheduled jobs that are due"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Get all active jobs
            cursor.execute('''
                SELECT * FROM scheduled_jobs 
                WHERE status = 'active'
            ''')
            jobs = cursor.fetchall()
            
            current_time = datetime.now()
            
            for job in jobs:
                # Check if job is due to run
                if is_job_due(job, current_time):
                    # Run the job in a separate thread
                    thread = threading.Thread(
                        target=run_scheduled_job,
                        args=(job,)
                    )
                    thread.start()
                    
        except Exception as e:
            logger.error(f"Error checking scheduled jobs: {e}")
        finally:
            conn.close()

def is_job_due(job, current_time):
    """Check if a job is due to run based on its frequency and time settings"""
    try:
        if job['frequency'] == 'hourly':
            return True
        elif job['frequency'] == 'daily':
            job_time = datetime.strptime(job['time'], '%H:%M').time()
            return current_time.time() >= job_time
        elif job['frequency'] == 'weekly':
            job_time = datetime.strptime(job['time'], '%H:%M').time()
            return (current_time.weekday() == job['day_of_week'] and 
                   current_time.time() >= job_time)
        elif job['frequency'] == 'monthly':
            job_time = datetime.strptime(job['time'], '%H:%M').time()
            return (current_time.day == job['day_of_month'] and 
                   current_time.time() >= job_time)
        return False
    except Exception as e:
        logger.error(f"Error checking if job is due: {e}")
        return False 