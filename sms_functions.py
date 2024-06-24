import requests
from database import get_database
import re
import asyncio
import json
import aiohttp

# Global Variables
api_key = ""
smsno = ""
urgent = ""
url_send = "https://sender.ge/api/send.php"
url_callback = "https://sender.ge/api/callback.php"
headers = {"Content-Type": "application/xml"}

db = get_database()
if db is None:
    print("Database is off.. working without it.")
    update_records = False
else:
    update_records = True
    collection = db["sent_and_delivered"]



async def sms_sending(message: str, target: str, max_retries: int = 3):  # Simply sends the SMS with API, gets response and inserts into mongodb.
    is_empty = True
    message_id = None
    retry_count = 0

    try:
        while is_empty and retry_count < max_retries:
            querystring = {
                "apikey": api_key,
                "destination": target,
                "content": message,
                "smsno": smsno,
                "urgent": urgent
            }
            response = requests.get(url_send, headers=headers, params=querystring)
            new_data = response.json()

            if response.status_code == 200:
                message_id = new_data['data'][0]['messageId']
                if message_id:
                    is_empty = False

                if message_id == '':
                    retry_count += 1
                    print(f"This is retry number {retry_count}")
                    await asyncio.sleep(1)  # Sleep for 1 second before the next retry
            else:
                # Handle the case when the response is not 200
                print(f"API request failed with status code {response.status_code}")

    except requests.exceptions.RequestException as e:
        # Handle exceptions when the URL is completely down
        print(f"API request failed with error: {e}")
        is_empty = True

    record = {
        "message_id": message_id or '',
        "sent_to": target,
        "sent_text": message,
        
    }
    
    if update_records:
        collection.insert_one(record)
    return {"Text": message, "Number": target}



async def check_delivery_reports(): #check for all records with empty message_id and if found - resends with sms_sending()
    empty_message_records = collection.find({"message_id": ''})
    for record in empty_message_records:
        sent_to = record['sent_to']
        sent_text = record['sent_text']

        querystring = {
            "apikey": api_key,
            "destination": sent_to,
            "content": sent_text,
            "smsno": smsno,
            "urgent": urgent
        }

        response = requests.get(url_send, params=querystring)
        new_data = response.json()
        message_id = new_data['data'][0]['messageId']

        if message_id:
            collection.update_one({"_id": record['_id']}, {"$set": {"message_id": message_id}})



async def check_delivery_against_api():
    query = {
        "statusId": {"$exists": False},
        "timestamp": {"$exists": False}
    }
    records = collection.find(query)
    num_records = collection.count_documents(query)
    
    if num_records == 0:
        print("No records found that meet the condition. Skipping execution.")
        return
    
    print(f"Found {num_records} record(s) that meet the condition.")
    
    async def process_record(record):
        message_id = record["message_id"]

        async with aiohttp.ClientSession() as session:
            params = {
                "apikey": api_key,
                "messageId": message_id
            }
            async with session.get(url_callback, params=params) as response:
                if response.status == 200:
                    response_text = await response.text()
                    try:
                        json_data = json.loads(response_text)
                        status_id = json_data["data"][0]["statusId"]
                        timestamp = json_data["data"][0]["timestamp"]

                        update_query = {"message_id": message_id}

                        if status_id == 1:
                            update = {
                                "$set": {
                                    "statusId": status_id,
                                    "timestamp": timestamp,
                                    "Delivery": True
                                }
                            }
                        elif status_id == 0:
                            update = {
                                "$set": {
                                    "statusId": status_id,
                                    "timestamp": timestamp,
                                    "Delivery": "Unknown"
                                }
                            }
                        else:
                            update = {
                                "$set": {
                                    "statusId": status_id,
                                    "timestamp": timestamp,
                                    "Delivery": False
                                }
                            }

                        # Update the record in MongoDB
                        collection.update_one(update_query, update)
                    except (json.JSONDecodeError, KeyError):
                        # Handle the case when the response is not valid JSON or expected fields are missing
                        print(f"Invalid response for message ID {message_id}")
                else:
                    # Handle the case when the API request fails
                    print(f"API request failed for message ID {message_id} with status code {response.status}")
                    response_text = await response.text()
                    if "no record found" in response_text:
                        update_query = {"message_id": message_id}
                        update = {
                            "$set": {
                                "statusId": 6,
                                "timestamp": "None",
                                "Delivery": False
                            }
                        }
                        collection.update_one(update_query, update)
                        print(f"Status Updated for no record found for {message_id}")
    await asyncio.gather(*[process_record(record) for record in records])



async def status_id_zero():
    query = {
        "statusId": 0
    }
    records = collection.find(query)
    num_records = collection.count_documents(query)
    if num_records == 0:
        print("No records found that meet the condition. Skipping execution.")
        return

    print(f"Found {num_records} record(s) that meet the condition.")

    async def process_record(record):
        message_id = record["message_id"]

        async with aiohttp.ClientSession() as session:
            params = {
                "apikey": api_key,
                "messageId": message_id
            }
            async with session.get(url_callback, params=params) as response:
                if response.status == 200:
                    response_text = await response.text()
                    try:
                        json_data = json.loads(response_text)
                        status_id = json_data["data"][0]["statusId"]
                        timestamp = json_data["data"][0]["timestamp"]
                        update_query = {"message_id": message_id}
                        update = None  # Initialize update variable

                        if status_id != 0:
                            if status_id == 1:
                                update = {
                                    "$set": {
                                        "statusId": status_id,
                                        "timestamp": timestamp,
                                        "Delivery": True
                                    }
                                }
                            else:
                                update = {
                                    "$set": {
                                        "statusId": status_id,
                                        "timestamp": timestamp,
                                        "Delivery": "Unknown"
                                    }
                                }

                        if update is not None:
                            # Update the record in MongoDB
                            collection.update_one(update_query, update)

                        if status_id in [0, 2, 3] and num_records >= 150:
                            # Set statusId to 5 and Delivery to False for all remaining records
                            collection.update_many({"statusId": 0}, {"$set": {"statusId": 5, "Delivery": False}})
                    except (json.JSONDecodeError, KeyError):
                        # Handle the case when the response is not valid JSON or expected fields are missing
                        print(f"Invalid response for message ID {message_id}")
                else:
                    # Handle the case when the API request fails
                    print(f"API request failed for message ID {message_id} with status code {response.status}")

    await asyncio.gather(*[process_record(record) for record in records])


async def status_id_five_six():
    query = {
        "statusId": {"$in": [5, 6]}
    }
    records = collection.find(query)
    num_records = collection.count_documents(query)
    if num_records == 0:
        print("No records found that meet the condition. Skipping execution.")
        return

    print(f"Found {num_records} record(s) that meet the condition.")

    async def process_record(record):
        message_id = record["message_id"]

        async with aiohttp.ClientSession() as session:
            params = {
                "apikey": api_key,
                "messageId": message_id
            }
            async with session.get(url_callback, params=params) as response:
                if response.status == 200:
                    response_text = await response.text()
                    try:
                        json_data = json.loads(response_text)
                        status_id = json_data["data"][0]["statusId"]
                        timestamp = json_data["data"][0]["timestamp"]
                        update_query = {"message_id": message_id}
                        update = None  # Initialize update variable

                        if status_id != 0:
                            if status_id == 1:
                                update = {
                                    "$set": {
                                        "statusId": status_id,
                                        "timestamp": timestamp,
                                        "Delivery": True
                                    }
                                }
                            else:
                                update = {
                                    "$set": {
                                        "statusId": status_id,
                                        "timestamp": timestamp,
                                        "Delivery": "Unknown"
                                    }
                                }

                        if update is not None:
                            # Update the record in MongoDB
                            collection.update_one(update_query, update)

                        if status_id in [0, 2, 3] and num_records >= 150:
                            # Set statusId to 5 and Delivery to False for all remaining records
                            collection.update_many({"statusId": {"$in": [5, 6]}}, {"$set": {"statusId": 5, "Delivery": False}})
                    except (json.JSONDecodeError, KeyError):
                        # Handle the case when the response is not valid JSON or expected fields are missing
                        print(f"Invalid response for message ID {message_id}")
                else:
                    # Handle the case when the API request fails
                    print(f"API request failed for message ID {message_id} with status code {response.status}")

    await asyncio.gather(*[process_record(record) for record in records])




 
