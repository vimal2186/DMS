from pymongo import MongoClient, ReadPreference # Import ReadPreference
from pymongo.server_api import ServerApi
from datetime import datetime, timedelta
from passlib.context import CryptContext
import logging

from backend.models import User, Person, DocumentFeedback # Import the User, Person, and DocumentFeedback models

MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "dms_db"

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Database:
    def __init__(self, uri, db_name):
        self.client = MongoClient(uri, server_api=ServerApi('1'))
        self.db = self.client[db_name]
        logger.info(f"Database instance created. Client ID: {id(self.client)}, DB ID: {id(self.db)}")
        try:
            # Send a ping to confirm a successful connection
            self.client.admin.command('ping')
            logger.info("Pinged your deployment. You successfully connected to MongoDB!")
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {e}")

    def get_collection(self, collection_name):
        # Ensure strong consistency for reads, especially for chat messages
        collection = self.db.get_collection(collection_name, read_preference=ReadPreference.PRIMARY)
        logger.info(f"Accessed collection '{collection_name}'. Collection ID: {id(collection)}")
        return collection

# Create a single instance of the database connection
db_connection = Database(MONGO_URI, DATABASE_NAME)
logger.info(f"Global db_connection instance created. ID: {id(db_connection)}")

# Dependency to get the database collection for documents
def get_document_collection():
    collection = db_connection.get_collection("documents")
    logger.debug(f"get_document_collection called. Collection ID: {id(collection)}")
    return collection

# Dependency to get the database collection for document chunks
def get_document_chunk_collection():
    collection = db_connection.get_collection("document_chunks")
    logger.debug(f"get_document_chunk_collection called. Collection ID: {id(collection)}")
    return collection

# Dependency to get the database collection for reminders
def get_reminder_collection():
    collection = db_connection.get_collection("reminders")
    logger.debug(f"get_reminder_collection called. Collection ID: {id(collection)}")
    return collection

# Dependency to get the database collection for chat messages
def get_chat_message_collection():
    collection = db_connection.get_collection("chat_messages")
    logger.debug(f"get_chat_message_collection called. Collection ID: {id(collection)}")
    return collection

# Dependency to get the database collection for conversations
def get_conversation_collection():
    collection = db_connection.get_collection("conversations")
    logger.debug(f"get_conversation_collection called. Collection ID: {id(collection)}")
    return collection

# Dependency to get the database collection for users
def get_user_collection():
    collection = db_connection.get_collection("users")
    logger.debug(f"get_user_collection called. Collection ID: {id(collection)}")
    return collection

# Dependency to get the database collection for persons
def get_person_collection():
    collection = db_connection.get_collection("persons")
    logger.debug(f"get_person_collection called. Collection ID: {id(collection)}")
    return collection

# Dependency to get the database collection for document feedback
def get_document_feedback_collection():
    collection = db_connection.get_collection("document_feedback")
    logger.debug(f"get_document_feedback_collection called. Collection ID: {id(collection)}")
    return collection

# User management functions
def create_user(user: User):
    users_collection = get_user_collection()
    user_dict = user.model_dump(by_alias=True, exclude_none=False) # Ensure _id: None is always present
    if '_id' in user_dict and user_dict['_id'] is None:
        user_dict.pop('_id')
    result = users_collection.insert_one(user_dict)
    user.id = result.inserted_id
    logger.info(f"User created with ID: {user.id}")
    return user

def get_user_by_username(username: str):
    users_collection = get_user_collection()
    user_data = users_collection.find_one({"username": username})
    if user_data:
        return User(**user_data)
    return None

def get_user_by_email(email: str):
    users_collection = get_user_collection()
    user_data = users_collection.find_one({"email": email})
    if user_data:
        return User(**user_data)
    return None

def create_admin_user_if_not_exists():
    admin_username = "admin"
    admin_email = "vimsyvimal@gmail.com"
    admin_password = "Vimal@350070" # This will be hashed

    users_collection = get_user_collection()
    existing_admin = users_collection.find_one({"username": admin_username})

    if not existing_admin:
        hashed_password = pwd_context.hash(admin_password)
        trial_start = datetime.utcnow()
        trial_end = trial_start + timedelta(days=30)

        admin_user = User(
            username=admin_username,
            password=hashed_password,
            email=admin_email,
            trial_start_date=trial_start,
            trial_end_date=trial_end,
            is_admin=True
        )
        create_user(admin_user)
        logger.info(f"Admin user '{admin_username}' created successfully.")
    else:
        logger.info(f"Admin user '{admin_username}' already exists.")

# Call this function to ensure admin user is created on startup
create_admin_user_if_not_exists()
