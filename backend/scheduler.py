import schedule
import time
import threading
from datetime import datetime
from plyer import notification
from .database import get_reminder_collection
from bson import ObjectId # Added this import

def check_reminders():
    """Checks for due reminders and sends notifications."""
    print("Checking for reminders...")
    reminder_collection = get_reminder_collection()
    now = datetime.utcnow()
    
    reminders = list(reminder_collection.find({"due_date": {"$lte": now}}))
    
    for reminder in reminders:
        reminder_id = reminder.get('_id') # Get the raw _id
        
        # If _id is None or not a valid ObjectId, log and delete it
        if not reminder_id or not isinstance(reminder_id, ObjectId):
            print(f"Deleting malformed reminder with missing or invalid ID: {reminder.get('message', 'Unknown')}")
            try:
                # Attempt to delete by any available identifier or the whole document if _id is truly missing
                if reminder_id: # If it's not None but invalid ObjectId
                    reminder_collection.delete_one({"_id": reminder_id})
                else: # If _id is None, try to delete by message and due_date if unique enough
                    reminder_collection.delete_one({"message": reminder.get('message'), "due_date": reminder.get('due_date')})
                print(f"Malformed reminder deleted from database.")
            except Exception as e:
                print(f"Error deleting malformed reminder: {e}")
            continue # Skip notification for this malformed reminder

        # Ensure reminder_id is a string for notification message
        str_reminder_id = str(reminder_id)

        notification.notify(
            title="DMS Reminder",
            message=f"Reminder for document: {reminder['message']}",
            app_name="DMS"
        )
        # Optionally, delete the reminder after notification
        # reminder_collection.delete_one({"_id": reminder_id}) # Use the valid ObjectId here
        print(f"Sent notification for reminder: {str_reminder_id}")

def run_scheduler():
    """Runs the scheduler in a separate thread."""
    schedule.every(1).minutes.do(check_reminders)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

def start_scheduler():
    """Starts the scheduler in a background thread."""
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    print("Scheduler started.")

# You would call start_scheduler() in your main application startup logic,
# for example, in the `backend/app.py` file using FastAPI's startup events.
