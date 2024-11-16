from flask import Flask, request
import threading
import requests

import time as t  # подключаем библиотеку для работы с временем
import logging
from telebot.types import LabeledPrice
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

import telebot
from telebot import types
from telegram.error import BadRequest
from telegram import ReplyKeyboardRemove
from flask_sqlalchemy import SQLAlchemy
import os
import ngrok

# my modules
import get_min_am
import db_module
import text_message
from get_data import config, get_from_env

db = SQLAlchemy()

app = Flask(__name__)

PAYMENT_TIMEOUT = 300

# Dictionary to keep track of pending payments
pending_payments = {}

new_user = ''

logger = telebot.logger  # create logger


# logging.getLogger("requests").setLevel(logging.WARNING)

logging.basicConfig(filename='payment.log', filemode='w', level=logging.DEBUG)

logger_2 = logging.getLogger(__name__)
logging.basicConfig(filename='payment.log', level=logging.INFO)
logger_2 .info('Started')

authtoken = get_from_env('ENV_NGROK_AUTHTOKEN')
print(authtoken)

listener = ngrok.forward("localhost:5000", authtoken=authtoken)
print(f"Ingress established at: {listener.url()}")


# Set webhook for the bot

bot = telebot.TeleBot(get_from_env("TELEGRAM_BOT_TOKEN"))
bot.set_webhook(url=f"{listener.url()}/{bot.token}")

app.config['SQLALCHEMY_DATABASE_URI'] = get_from_env('DATABASE_URL')

db.init_app(app)



inline_keyboard = types.InlineKeyboardMarkup()
# create keyboard

pay_button_text = config['BUTTON1']  # latte
pay_button = InlineKeyboardButton(pay_button_text, pay=True, callback_data=pay_button_text)

terms_button_text = config['BUTTON2']  # terms
terms_button = InlineKeyboardButton(terms_button_text, callback_data=terms_button_text)

help_button_text = config['BUTTON3']  # help
help_button = InlineKeyboardButton(help_button_text, callback_data=help_button_text)

inst_button_text = config['BUTTON4']  # Instruction
inst_button = InlineKeyboardButton(inst_button_text, callback_data=inst_button_text)

keyboard_2 = InlineKeyboardMarkup([[pay_button], [terms_button], [help_button], [inst_button]])
print(config['BUTTON1'])

bot = telebot.TeleBot(get_from_env("TELEGRAM_BOT_TOKEN"))
admin_id = get_from_env("ADMIN_ID")
print(f'{admin_id} - admin_id')
authtoken = get_from_env("ENV_NGROK_AUTHTOKEN")


# print(authtoken)


@app.route(f'/{bot.token}', methods=['POST'])
def process():
    json_str = request.stream.read().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200


@bot.message_handler(commands=['start'])
def command_start(message):
    global new_user

    keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)  # Connect the keyboard
    button_phone = types.KeyboardButton(text="Відправити номер", request_contact=True)  # Specify the name of the
    # button that the user will see
    keyboard.add(button_phone)  # Add this button
    print(f'{message.chat.id}-message.chat.id')
    new_user = message.from_user.id
    m1 = f'Привiт, {message.from_user.first_name}'
    bot.send_message(message.chat.id, m1)
    bot.send_message(message.chat.id, config["CONTACT_REQUEST"], reply_markup=keyboard)


def send_message_to_admin(update, context):
    if update.message.chat.id == admin_id:
        bot.send_message(chat_id=admin_id, text="Привiт, адмiнiстратор!")
        bot.send_message(admin_id, f'user {new_user} in chat!')


@bot.message_handler(content_types=[
    'contact'])  # Announced a branch in which we prescribe logic in case the user decides to send a phone number :)
def contact(message):
    if message.contact is not None:  # If the send object <strong> contact </strong> is not zero
        print(message.contact)
        keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True,
                                             one_time_keyboard=False)  # Connect the keyboard
        button_phone = types.KeyboardButton(text="Відправити місцезнаходження",
                                            request_location=True)  # Specify the name of the
        # button that the user will see
        keyboard.add(button_phone)  # Add this button

        bot.send_message(message.chat.id, config["LOCATION_REQUEST"], reply_markup=keyboard)

        # bot.send_message(message.chat.id, text_message.generate_start(), reply_markup=keyboard_2)
        with db_module.connect_db() as cursor:  # open.py DB
            # should chek if id_telegram is unique
            cursor.execute(
                f"""SELECT * FROM customers WHERE telegram_id={message.from_user.id};"""
            )
            if cursor.rowcount:
                print('Это имя уже занято.')
                print(f"[INFO] {message.from_user.id} exists")
            else:
                # save to database
                mas = message.from_user.first_name, message.from_user.last_name, message.contact.phone_number, \
                    message.from_user.id
                # print(mas)
                with db_module.connect_db() as cursor:  # open.py DB
                    insert_query = "INSERT INTO customers (customer_fname, customer_lname, phone_number, telegram_id) VALUES " \
                                   "(%s, %s, %s, %s)"
                    print('Ок.')
                    cursor.execute(insert_query, mas)
                    print("[INFO] Data was succefully inserted")


@bot.message_handler(content_types=['location'])
def contact(message):
    if message.location is not None:  # If the send object <strong> contact </strong> is not zero
        print(message.location)
    # print(message)

    markup = types.ReplyKeyboardRemove()
    # Use the bot.send_message function with the ReplyKeyboardRemove object
    bot.send_message(message.chat.id, 'The keyboard used and has been removed.', reply_markup=markup)

    bot.send_message(message.chat.id, text_message.generate_start(), reply_markup=keyboard_2)


@bot.message_handler(content_types=['text'])
def handle_text_message(message):
    bot.send_message(message.chat.id, text_message.generate_start(), reply_markup=keyboard_2)


@bot.callback_query_handler(func=lambda call: call.data == pay_button_text)
def command_pay(call: types.CallbackQuery):
    # print(call)

    print('i am in buy')

    if get_from_env("PAYMENT_TOKEN").split(':')[1] == 'TEST':
        # print(get_from_env("PAYMENT_TOKEN"))
        bot.send_message(call.message.chat.id, "Тестовuй платiж!!!")
    chat_id = call.message.chat.id
    date = call.message.date
    bot.send_message(chat_id, text_message.generate_pay(), parse_mode='Markdown')
    send_invoice(chat_id, date)


def send_invoice(chat_id, date):
    chat_id = chat_id
    title = config['PRODUCT']
    description = config['PRODUCT_desc']
    payload = f'invoice 6'
    provider_token = get_from_env("PAYMENT_TOKEN")
    currency = 'UAH'
    correct_am = int(get_min_am.get_min_am())
    amount = 4060
    # if amount < telegram amount - pay does not happen
    if amount < correct_am:
        print('Oops! Price must be higher')
        amount = correct_am + 1
        print(amount)
    price = LabeledPrice(title, amount)
    prices = [price]
    # print(prices)
    start_parameter = title
    photo_url = 'https://assets2.devourtours.com/wp-content/uploads/ordering-coffee-in-italian-latte-1.jpg'
    # prices = [{'label': 'latte', 'amount': amount}]
    try:
        bot.send_invoice(chat_id, title, description, payload, provider_token, currency, prices, photo_url=photo_url,
                         photo_height=100, photo_width=100, photo_size=200, start_parameter=start_parameter)
        with db_module.connect_db() as cursor:  # open.py DB
            status = 'create'
            y = db_module.get_id(chat_id)
            mas = status, y, 1
            insert_query = "INSERT INTO purchases (status,customer_id,store_id) VALUES (%s,%s,%s)"
            # print('Ок.')
            cursor.execute(insert_query, mas)
    except BadRequest as e:
        print('not send')
        print(e)
    pending_payments[chat_id] = date
    bot.send_message(admin_id, f'An invoice sent for user {new_user}')


@bot.callback_query_handler(func=lambda call: call.data == terms_button_text)
def command_terms(call: types.CallbackQuery):
    bot.send_message(chat_id=call.message.chat.id, text=text_message.generate_terms(), reply_markup=keyboard_2)


@bot.callback_query_handler(func=lambda call: call.data == help_button_text)
def command_pay(call: types.CallbackQuery):
    bot.send_message(chat_id=call.message.chat.id, text=text_message.generate_help(), reply_markup=keyboard_2)


@bot.callback_query_handler(func=lambda call: call.data == inst_button_text)
def command_inst(call: types.CallbackQuery):
    bot.send_message(chat_id=call.message.chat.id, text=text_message.generate_inst(), reply_markup=keyboard_2)


@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout_query(pre_checkout_query):
    # print(pre_checkout_query)
    try:
        global new_user
        result = bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
        if result:
            # The answer was successfully sent
            admin_chat_id = admin_id
            bot.send_message(admin_chat_id, f'A pre-checkout for user {new_user} query was successful!')
        else:
            # The answer was not sent
            bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False, error_message='Спробуйте ще раз')
            # bot.send_message(admin_id, f'A pre-checkout query for user {message.from_user.id} was bad!')
    except telebot.apihelper.ApiException as e:
        # An error occurred while sending the answer
        print(f"An error occurred: {e.result.text}")


# price with 2 symbol after dote
def two_symbol(x):
    x = "{:.2f}".format(x)
    return x


@bot.message_handler(content_types=['successful_payment'])
def successful_payment_handler(message):
    new_user = ''
    # Payment was successful, remove the user's chat ID from the pending payments dictionary
    if message.chat.id in pending_payments:
        del pending_payments[message.chat.id]
    # Send a confirmation message to the user
    bot.send_message(message.chat.id,
                     'Дякуємо за оплату latte `{} {}`!'
                     '\n Використовуйте Latte знову, щоб отримати лате для свого друга!'.format(
                         two_symbol(message.successful_payment.total_amount / 100),
                         message.successful_payment.currency),
                     parse_mode='Markdown')
    telegram_payment_charge_id = message.successful_payment.telegram_payment_charge_id
    provider_payment_charge_id = message.successful_payment.provider_payment_charge_id
    bot.send_message(admin_id, f'A Payment was successful! user {message.from_user.id}')
    print(telegram_payment_charge_id, provider_payment_charge_id)
    with db_module.connect_db() as cursor:  # open.py DB
        # update TABLE set FIELD = VALUE where id = (select max(id) from TABLE);
        sql_update = "UPDATE purchases SET status=%s, receipt_date=NOW(),telegram_payment_charge_id=%s, provider_payment_charge_id=%s WHERE purchase_id=(SELECT max(purchase_id) FROM purchases)"
        val = ('successful', telegram_payment_charge_id, provider_payment_charge_id)
        cursor.execute(sql_update, val)
        print('Ок.')


def check_pending_payments():
    while True:
        global new_user
        # Check for any pending payments that have exceeded the timeout period example 5 min
        for chat_id, timestamp in list(pending_payments.items()):
            if (timestamp + PAYMENT_TIMEOUT) < t.time():
                # Payment has timed out, remove the user's chat ID from the pending payments dictionary
                del pending_payments[chat_id]
                # Send a follow-up message to the user
                bot.send_message(chat_id, 'Payment failed or timed out. Please try again or contact support for /help')
                bot.send_message(admin_id, f'A Payment was not successful! user {new_user}')
                new_user = ''
                with db_module.connect_db() as cursor:  # open.py DB
                    sql_update = "UPDATE purchases SET status=%s WHERE purchase_id=(SELECT max(purchase_id) FROM " \
                                 "purchases)"
                    val = ('unsuccessful',)
                    cursor.execute(sql_update, val)
                new_user = ''
                print('Ок.')

        t.sleep(60)


if __name__ == '__main__':
    if listener:
        # Run Flask app
        thread = threading.Thread(target=check_pending_payments)
        thread.start()
        app.run(host='localhost', port=5000)
        current_t = t.strftime("%H:%M:%S", t.localtime())
        logging.info("%s - start app" % current_t)
        logger.info("bot працює")
    else:
        print("ngrok URL not found. Webhook not set.")
        logger.warning("bot не працює")