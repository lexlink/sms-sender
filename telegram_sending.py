import telegram
from database import get_database
import datetime

bot = telegram.Bot(token='')

db = get_database()

if db is None:
    print("Database is off.. working without it.")
    telegram_database_off = True
else:
    telegram_database_off = False
    telegram_collection = db["telegram_users"]
    telegram_sent_messages = db["telegram_sent_messages"]


async def telegram_sending(message: str, target: str):
    if telegram_database_off:
        print("Telegram DB is off, can't work")
        return {'status': 'failed'}

    # Split the message to extract the client number and the text
    split_message = message.split(' # ')
    client_number = split_message[0][:4]  # Extract the first 4 digits as the client number
    text = split_message[1] if len(split_message) > 1 else ''

    # Look up the users with the specified client number
    users = telegram_collection.find({'client_number': client_number})
    for user in users:
        # Check if the user has the target (mobile) number
        if user['mobile_number'] == target:
            # Send the message to the user
            bot.send_message(chat_id=user['telegram_id'], text=f"{client_number} {text}")

            # Insert the message details into the telegram_sent_messages collection
            message_doc = {
                'chat_user': user['telegram_id'],
                'sent_text': message,
                'sent_number': target,
                'delivered': True,
                'timestamp': datetime.datetime.now()
            }
            telegram_sent_messages.insert_one(message_doc)

    return {'status': 'success'}
