from pymongo import MongoClient
from pymongo.server_api import ServerApi

MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "dms_db"

class Database:
    def __init__(self, uri, db_name):
        self.client = MongoClient(uri, server_api=ServerApi('1'))
        self.db = self.client[db_name]
        try:
            # Send a ping to confirm a successful connection
            self.client.admin.command('ping')
            print("Pinged your deployment. You successfully connected to MongoDB!")
        except Exception as e:
            print(e)

    def get_collection(self, collection_name):
        return self.db[collection_name]

# Create a single instance of the database connection
db_connection = Database(MONGO_URI, DATABASE_NAME)

# Dependency to get the database collection for documents
def get_document_collection():
    return db_connection.get_collection("documents")

# Dependency to get the database collection for reminders
def get_reminder_collection():
    return db_connection.get_collection("reminders")
