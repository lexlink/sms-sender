import telegram
from pymongo import DESCENDING
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response
import aiocron
import urllib.parse
import datetime
from database import get_database
from sms_functions import sms_sending, check_delivery_against_api, check_delivery_reports, status_id_zero
from telegram_sending import telegram_sending
import logging

logging.basicConfig(level=logging.DEBUG)   # add this line
logger = logging.getLogger("foo")

db = get_database()
if db is None:
    print("Database is off.. working without it.")
    run_cron = False
    run_records = False
else:
    run_cron = True
    run_records = True

collection = db["sent_and_delivered"]
tel_collection = db["telegram_sent_messages"]
bot = telegram.Bot(token='')
app = FastAPI()
templates = Jinja2Templates(directory="templates")


if run_cron:
    @aiocron.crontab("*/2 * * * *")
    async def run_check_delivery_reports():
        await check_delivery_reports()

    @aiocron.crontab("*/5 * * * *")  # Run every 5
    async def run_check_delivery_against_api():
        await check_delivery_against_api()
        
    @aiocron.crontab("0 */3 * * *") # Run every 3 hours
    #@aiocron.crontab("*/1 * * * *")  # Run every 5
    async def run_status_id_zero():
        await status_id_zero()


    @aiocron.crontab('0 0 */5 * *')  # Schedule every two days at midnight
    async def delete_old_data_from_database():
        # Calculate the date threshold for deletion
        threshold = datetime.datetime.now() - datetime.timedelta(days=2)

        # Delete old SMS records
        sms_records = collection.find({"date": {"$lt": threshold}})
        for sms in sms_records:
            # Delete the SMS record from the database
            collection.delete_one({"_id": sms["_id"]})

        # Delete old Telegram records
        telegram_records = tel_collection.find({"date": {"$lt": threshold}})
        for telegram in telegram_records:
            # Delete the Telegram record from the database
            tel_collection.delete_one({"_id": telegram["_id"]})





@app.get('/records', response_class=HTMLResponse)
async def records(request: Request, sort: str = None):
    if not run_records:
        return templates.TemplateResponse("records.html", {"request": request,
                                                           "error_message": "Database is not available, no records"})
    # Fetch the latest 100 SMS records
    sms_records = collection.find().sort('_id', DESCENDING).limit(500)
    # Fetch the latest 100 Telegram records
    telegram_records = tel_collection.find().sort('_id', DESCENDING).limit(20)
    sms_count = collection.count_documents({})
    pending_count = collection.count_documents({"statusId": 0, "timestamp": None})
    delivered_count = collection.count_documents({"statusId": 1})
    undelivered_count = collection.count_documents({"statusId": 2})
    deleted_by_provider = collection.count_documents({"statusId": 3})
    if sort:
        if sort == 'message_id_asc':
            sms_records = sms_records.sort('message_id', 1)
        elif sort == 'message_id_desc':
            sms_records = sms_records.sort('message_id', -1)
        elif sort == 'status_id_asc':
            sms_records = sms_records.sort('statusId', 1)
        elif sort == 'status_id_desc':
            sms_records = sms_records.sort('statusId', -1)
        elif sort == 'timestamp_asc':
            sms_records = sms_records.sort('timestamp', 1)
        elif sort == 'timestamp_desc':
            sms_records = sms_records.sort('timestamp', -1)

    return templates.TemplateResponse("records.html", {"request": request, "sms_records": sms_records,
                                                       "telegram_records": telegram_records, "sms_count": sms_count,
                                                       "pending_count": pending_count,
                                                       "delivered_count": delivered_count,
                                                       "undelivered_count": undelivered_count,
                                                       "deleted_by_provider": deleted_by_provider})


@app.get('/search', response_class=HTMLResponse)
async def search(request: Request, search_number: str):
    # Check if the search number is empty
    if not search_number:
        # Show all records when search number is empty
        sms_records = collection.find().sort('_id', DESCENDING).limit(500)
        telegram_records = tel_collection.find().sort('_id', DESCENDING).limit(500)
        sms_count = collection.count_documents({})
        telegram_count = tel_collection.count_documents({})
    else:
        # Perform the search query using the provided number
        search_query = {"$or": [{"sent_to": search_number}, {"sent_number": search_number}]}
        sms_records = collection.find(search_query).sort('_id', DESCENDING).limit(500)
        telegram_records = tel_collection.find(search_query).sort('_id', DESCENDING).limit(500)
        sms_count = collection.count_documents(search_query)
        telegram_count = tel_collection.count_documents(search_query)
        pending_count = collection.count_documents({"statusId": 0, "timestamp": None})

    return templates.TemplateResponse("records.html", {"request": request, "sms_records": sms_records,
                                                       "telegram_records": telegram_records,
                                                       "sms_count": sms_count,
                                                       "telegram_count": telegram_count,
                                                       "pending_count": pending_count})


@app.post("/channel")
async def which_channel(request: Request):
    content = await request.body()

    # Decode the content using URL decoding and WINDOWS-1251 encoding
    decoded_content = urllib.parse.unquote(content.decode(), encoding='WINDOWS-1251')

    # Extract the values from the decoded content
    form_data = urllib.parse.parse_qs(decoded_content)
    message = form_data.get('message', [''])[0]
    target = form_data.get('target', [''])[0]

    translations = {
	"Ручной тест": "ტესტი/TEST/ТЕСТ",
        "Взятие на охрану": "დაცვაზე აყვანა/System Armed/Взятие на охрану",
        "Снятие с охраны": "დაცვიდან მოხსნა/System Disarmed/Снятие с охраны",
        "Взятие на охрану ключом": "დაცვაზე აყვანა/System Armed/Взятие на охрану ключом",
        "Снятие с охраны ключом": "დაცვიდან მოხსნა/System Disarmed/Снятие с охраны ключом",
        "Тревожная кнопка": "საგანგაშო ღილაკი/Panic Button/Тревожная кнопка",
        "ВОССТ: Тревожная кнопка": "საგანგაშო ღილაკი: აღდგენა/Panit Button Restore/ВОССТ: Тревожная кнопка",
        "ВОССТ: Пожарная тревога": "სახანძრო განგაშის აღდგენა/File Alarm Restore/ВОССТ Пожарная тревога",
        "Тревога по зоне": "ზონის განგაში/Zone Alarm/Тревога по зоне",
        "Общая тревога": "საერთო განგაში/General Alarm/Общая тревога",
        "ВОССТ: Общая тревога" : "საერთო განგაში: აღდგენა/General Alarm Restore/ВОССТ Общая тревога",
        "Пожарная тревога": "სახანძრო განგაში/Fire Alarm/Пожарная тревога",
        "Разряд аккумулятора": "დამჯდარი ელემენტი/Low battery/Разряд аккумулятора",
        "'Зависание' панели": "გაჭედილ' პანელი/Panel Hang/'Зависание' панели",
        "Неисправность сети 220": "დენის წასვლა/Power outage/Неисправность сети 220",
        "ВОССТ: Неисправность сети 220": "დენის წასვლა: აღდგენა/Power Outage Restore/ВОССТ Неисправность сети 220"
    }


    # Split the message into code and original string
    code, original_string= message.split(" # ")

    # Check if the original string is in the translations dictionary
    if original_string in translations:
        # Get the translated value from the translations dictionary
        translated_value = translations[original_string]

        # Replace the original string with the translated value
        translated_message = f"{code} # {translated_value}"
    else:
        print("Translation not found for the original string:", original_string)
        return "Invalid message"  # Return an error response if translation not found

    if len(target) == 9:
        response = await sms_sending(translated_message, target)
        xml_response = generate_xml_response()
        return Response(content=xml_response, media_type="application/xml")
    elif len(target) == 10 and target.startswith('8'):
        new_target = target[1:]
        response = await telegram_sending(translated_message, new_target)
        xml_response = generate_xml_response()
        return Response(content=xml_response, media_type="application/xml")
    else:
        return "Invalid target number"


def generate_xml_response():
    response = '<?xml version="1.0" encoding="utf-8"?>'
    response += '<response>'
    response += '<SMS_SENT>1</SMS_SENT>'
    response += '<SMS_CLOSED>1</SMS_CLOSED>'
    response += '<errors></errors>'
    response += '</response>'
    return response
