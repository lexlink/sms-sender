from pymongo import MongoClient
import time


def get_database():
    while True:
        try:
            client = MongoClient("mongodb://",
                                 username="",
                                 password="",
                                 authSource="SMS_SENDING")
            db = client["SMS_SENDING"]
            return db  # Return the database object
        except Exception as e:
            print(f"Error connecting to the database: {e}")
            print("Retrying in 20 minutes...")
            time.sleep(1200)  # Wait for 20 minutes (1,200 seconds)
