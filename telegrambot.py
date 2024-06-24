from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from database import get_database

# Setup MongoDB connection
db = get_database()
collection = db["telegram_users"]


# Define command handlers
def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="""გამარჯობა, ეს არის ომეგა მ.ბ.რ. ბოტი. დასარეგისტრირებლად გთხოვთ აკრიფოთ /register
                              \nHi! This is a registration bot. To register, please send the /register command.
                              \nЗдравствуйте, это бот Омега МБР - для регистраций напишите /register.""")


def register(update, context):
    context.user_data['state'] = 'register_client_number'
    context.bot.send_message(chat_id=update.effective_chat.id, text="""გთხოვთ აკრიფოთ თქვენი ობიექტის ნომერი: მაგალითად 0001
                              \nPlease enter your 4-digit client number: example 0001
                              \nпожалуйста напишуте свой номер объекта. Например 0001""")


def add(update, context):
    context.user_data['state'] = 'add_client_number'
    context.bot.send_message(chat_id=update.effective_chat.id, text="გთხოვთ შეიყვანოთ დამატებითი 4 ციფრიანი ნომერი.")


def remove(update, context):
    user = collection.find_one({'telegram_id': update.effective_chat.id})
    if user and 'client_number' in user:
        numbers = user['client_number']
        context.user_data['state'] = 'remove_client_number'
        context.user_data['numbers'] = numbers
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"თქვენი ნომრები არის: {', '.join(numbers)}. რომლის წაშლა გნებავთ?")
    else:
        context.bot.send_message(chat_id=update.effective_chat.id, text="თქვენ არ გაქვთ დარეგისტრირებული ნომერი")

def unregister(update, context):
    collection.delete_one({'telegram_id': update.effective_chat.id})
    context.bot.send_message(chat_id=update.effective_chat.id, text="""თქვენ წარმატებით წაშალეთ რეგისტრაცია.
                                    \nYou have been successfully unregistered.
                                    \nВы успешно сняты с регистрации.""")

def echo(update, context):
    state = context.user_data.get('state')
    if state == 'register_client_number':
        client_number = update.message.text.strip()
        if client_number.isdigit() and len(client_number) == 4:
            context.user_data['client_number'] = client_number
            context.user_data['state'] = 'register_mobile_number'
            context.bot.send_message(chat_id=update.effective_chat.id, text="""გთხოვთ აკრიფოთ ტელეფონის ნომერი, რომელიც იწყება 5–ით.
              მაგალითად: 577951200 (+995 ან 0–ის გარეშე)
              \nPlease input your phone number that starts with 5, for example: 577951200 (without +995 or 0)
              \nПожалуйста введите номер телефона который начинается с цифры 5, на пример: 577951200 (без +995 или 0)""")
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="არასწორი ობიექტის ნომერი. გთხოვთ აკრიფოთ 4 ციფრიანი ნომერი.")
    elif state == 'register_mobile_number':
        mobile_number = update.message.text.strip()
        if mobile_number.isdigit() and len(mobile_number) == 9 and mobile_number.startswith('5'):
            user_data = {
                'telegram_id': update.effective_chat.id,
                'client_number': [context.user_data.get('client_number')],
                'mobile_number': mobile_number
            }
            collection.insert_one(user_data)
            context.user_data.clear()
            context.bot.send_message(chat_id=update.effective_chat.id, text="""მადლობა, რეგისტრაცია დასრულებულია.
                                    \nThank you for registering!
                                    \nСпасибо за регистрацию!""")
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="არასწორი ტელეფონის ნომერი. გთხოვთ აკრიფოთ 9–ციფრიანი ნომერი რომელიც იწყება 5–ით.")
    elif state == 'add_client_number':
        client_number = update.message.text.strip()
        if client_number.isdigit() and len(client_number) == 4:
            collection.update_one({'telegram_id': update.effective_chat.id}, {'$push': {'client_number': client_number}})
            context.bot.send_message(chat_id=update.effective_chat.id, text="Client number added.")
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="არასწორი ობიექტის ნომერი. გთხოვთ აკრიფოთ 4 ციფრიანი ნომერი.")
    elif state == 'remove_client_number':
        client_number = update.message.text.strip()
        numbers = context.user_data.get('numbers')
        if client_number in numbers:
            numbers.remove(client_number)
            collection.update_one({'telegram_id': update.effective_chat.id}, {'$set': {'client_number': numbers}})
            context.bot.send_message(chat_id=update.effective_chat.id, text="Client number removed.")
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text="არასწორი ობიექტის ნომერი. გთხოვთ აკრიფოთ ნომერი თქვენი დარეგისტრირებული ობიექტების სიიდან.")
    else:
        context.bot.send_message(chat_id=update.effective_chat.id, text="გთხოვთ გამოიყენოთ მხოლოდ ბრძანებები, მაგალითად :  /register ან /unregister.")


def main() -> None:
    # Create the EventHandler and pass it your bot's token
    updater = Updater("", use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # Add command handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("register", register))
    dp.add_handler(CommandHandler("add", add))
    dp.add_handler(CommandHandler("remove", remove))
    dp.add_handler(CommandHandler("unregister", unregister))

    # Add echo handler for other messages
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

    # Start the bot
    updater.start_polling()
    updater.idle()
if __name__ == '__main__':
    main()
