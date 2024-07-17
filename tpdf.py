import time
import telebot
from telebot import types
import os
from datetime import datetime
from flask import Flask, request

# Enable logging
import logging
logger = telebot.logger
telebot.logger.setLevel(logging.INFO)  # Outputs debug messages to console.

# Initialize bot with your token
bot = os.getenv("BOT_TOKEN")

# Flask app
app = Flask(__name__)

# Dictionary to map callback data to PDF names
callback_data_map = {}                                  
# Whitelisted chat IDs
whitelisted_chat_ids = {1276272528, 6452553052, 5627720740, 6556467986}
# Admin ID
admin_id = 1276272528

# User state management
user_states = {}

# Questions to ask the user
questions = [
    "What is your name?",
    "How old are you?",
    "Are you male or female?",
    "What is your highest level of education?",
    "What is your phone number?",
    "What is your email address?",
    "What is your blood group?",
    # Add more questions as needed
]

# Function to get the next question for the user
def get_next_question(user_id):
    if user_id not in user_states:
        user_states[user_id] = {'question_index': 0, 'answers': []}
    current_state = user_states[user_id]
    if current_state['question_index'] < len(questions):
        return questions[current_state['question_index']]
    else:
        return None

# Function to save user's answer and get the next question
def save_answer_and_get_next(user_id, answer):
    if user_id in user_states:
        current_state = user_states[user_id]
        current_state['answers'].append(answer.text)
        current_state['question_index'] += 1
        bot.forward_message(admin_id, user_id, answer.message_id)
        return get_next_question(user_id)
    else:
        return None

# Function to forward messages to admin
def forward_to_admin(message):
    bot.forward_message(admin_id, message.chat.id, message.message_id)

# Function to save pdf link to file with the new format
def save_pdf_link(pdf_name, file_id):
    pdf_name = pdf_name.replace(' ', '_')
    pdf_links_path = os.path.join('assets', 'pdf_links.txt')

    with open(pdf_links_path, 'a') as file:
        file.write(f'{pdf_name}:{file_id}\n')

def pdf_name_exists(pdf_name):
    pdf_name = pdf_name.replace(' ', '_')
    pdf_links_path = os.path.join('assets', 'pdf_links.txt')

    if os.path.exists(pdf_links_path):
        with open(pdf_links_path, 'r') as file:
            for line in file:
                try:
                    name, file_id = line.strip().split(':')
                    if name == pdf_name:
                        return True
                except ValueError:
                    logging.warning(f"Unexpected format in line: {line.strip()}")
                    continue
    return False

# Function to handle the 'next_page' callback
@bot.callback_query_handler(func=lambda call: call.data == 'next_page')
def handle_next_page(call):
    user_id = call.from_user.id
    initialize_pagination(user_id)

    current_page = user_states[user_id]['current_page']
    next_page = current_page + 1

    buttons = generate_pdf_buttons(page=next_page)
    markup = types.InlineKeyboardMarkup()
    if buttons:
        for button in buttons:
            markup.add(button)
        if next_page > 1:
            markup.add(types.InlineKeyboardButton(text='Previous', callback_data='prev_page'))
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
        update_current_page(user_id, next_page)
    else:
        bot.answer_callback_query(call.id, "No more PDFs found.")

# Function to handle the 'prev_page' callback
@bot.callback_query_handler(func=lambda call: call.data == 'prev_page')
def handle_previous_page(call):
    user_id = call.from_user.id
    initialize_pagination(user_id)

    current_page = user_states[user_id]['current_page']
    previous_page = max(1, current_page - 1)

    buttons = generate_pdf_buttons(page=previous_page)
    markup = types.InlineKeyboardMarkup()
    if buttons:
        for button in buttons:
            markup.add(button)
        markup.add(types.InlineKeyboardButton(text='Next', callback_data='next_page'))
        if previous_page > 1:
            markup.add(types.InlineKeyboardButton(text='Previous', callback_data='prev_page'))
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
        update_current_page(user_id, previous_page)
    else:
        bot.answer_callback_query(call.id, "No more PDFs found.")

# Constants for pagination
ITEMS_PER_PAGE = 10

# Function to generate paginated InlineKeyboardButtons for PDFs
def generate_pdf_buttons(page=1):
    buttons = []
    start_index = (page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    counter = start_index

    if os.path.exists('assets/pdf_links.txt'):
        with open('assets/pdf_links.txt', 'r') as file:
            lines = file.readlines()[start_index:end_index]
            for line in lines:
                parts = line.strip().split(':')
                if len(parts) >= 2:
                    name = ':'.join(parts[:-1])
                    callback_data = f'pdf{counter}'
                    callback_data_map[callback_data] = name
                    button_text = f'{name}'
                    buttons.append(types.InlineKeyboardButton(text=button_text, callback_data=callback_data))
                    counter += 1

    if os.path.getsize('assets/pdf_links.txt') > end_index * len(max(lines, key=len)):
        buttons.append(types.InlineKeyboardButton(text='Next', callback_data='next_page'))

    return buttons

# Handler for /pdfs command with pagination
@bot.message_handler(commands=['pdfs', 'pdfharu'])
def show_pdfs(message):
    page = 1
    markup = types.InlineKeyboardMarkup()
    buttons = generate_pdf_buttons(page)
    if buttons:
        for button in buttons:
            markup.add(button)
        bot.send_message(message.chat.id, 'Select a PDF:', reply_markup=markup)
    else:
        bot.send_message(message.chat.id, 'No PDFs found.')

# Function to check if the user has already downloaded a PDF today
def has_downloaded_today(user_id):
    privileged_users = {1276272528, 6556467986}
    if user_id in privileged_users or user_id in whitelisted_chat_ids:
        return False
    filename = os.path.join('caches', f'user_{user_id}.txt')
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            date_str = file.read().strip()
            last_download_date = datetime.strptime(date_str, '%Y_%m_%d')
            return last_download_date.date() == datetime.now().date()
    return False

# Function to update the download date for a user
def update_download_date(user_id):
    filename = os.path.join('caches', f'user_{user_id}.txt')

    with open(filename, 'w') as file:
        date_str = datetime.now().strftime('%Y_%m_%d')
        file.write(date_str)

# Handlers
@bot.message_handler(commands=['startme', 'helpme'])
def send_welcome(message):
    forward_to_admin(message)
    bot.reply_to(message, "Welcome to the PDF Bot! Use /pdfs to get a list of available PDFs.")
    question = get_next_question(message.from_user.id)
    if question:
        bot.send_message(message.chat.id, question)

@bot.message_handler(content_types=['document'])
def auto_save_pdf(message):
    forward_to_admin(message)
    document = message.document
    if document.mime_type == 'application/pdf':
        pdf_name = document.file_name
        if not pdf_name_exists(pdf_name):
            pdf_file_id = document.file_id
            save_pdf_link(pdf_name, pdf_file_id)
            bot.reply_to(message, f'PDF "{pdf_name}" saved automatically!')
        else:
            bot.reply_to(message, f'PDF "{pdf_name}" already exists.')

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    bot.answer_callback_query(call.id)
    user_id = call.from_user.id
    full_name = call.from_user.full_name
    callback_data = call.data

    if callback_data.startswith('pdf'):
        handle_pdf_callback(call, callback_data)
    else:
        pass

def handle_pdf_callback(call, callback_data):
    user_id = call.from_user.id
    pdf_name = callback_data_map.get(callback_data, None)
    pdf_file_id = None

    if pdf_name:
        with open('assets/pdf_links.txt', 'r') as file:
            for line in file:
                parts = line.strip().split(':')
                if len(parts) == 2:
                    name, file_id = parts
                    if name == pdf_name:
                        pdf_file_id = file_id
                        break

    if pdf_file_id:
        if not has_downloaded_today(user_id):
            bot.send_message(call.message.chat.id, "Please, take only one PDF per day. Thank you! ")
            bot.send_document(call.message.chat.id, pdf_file_id)
            update_download_date(user_id)
            bot.send_message(admin_id, f"User {call.from_user.full_name} ({user_id}) downloaded the PDF: {pdf_name}.")
        else:
            bot.send_message(call.message.chat.id, "You have already downloaded a PDF today. Please try again tomorrow.")
            bot.send_message(admin_id, f"User {call.from_user.full_name} ({user_id}) tried to download the PDF: {pdf_name} but had already downloaded one today.")
    else:
        bot.send_message(call.message.chat.id, "Sorry, the requested PDF could not be found.")

@bot.message_handler(func=lambda message: message.chat.id not in whitelisted_chat_ids)
def handle_non_whitelisted(message):
    bot.reply_to(message, "You are not authorized to use this bot.")
    forward_to_admin(message)

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    question = get_next_question(user_id)
    if question:
        bot.send_message(message.chat.id, question)
    else:
        bot.reply_to(message, "Thank you! Your answers have been recorded.")
        forward_to_admin(message)

# Function to initialize pagination state for a user
def initialize_pagination(user_id):
    if user_id not in user_states:
        user_states[user_id] = {}
    if 'current_page' not in user_states[user_id]:
        user_states[user_id]['current_page'] = 1

# Function to update the current page for a user
def update_current_page(user_id, page):
    if user_id in user_states:
        user_states[user_id]['current_page'] = page

# Webhook URL (you need to set this to your Render URL)
WEBHOOK_URL = 'https://tpdf.onrender.com/'  # Update this URL

@app.route('/' + bot.token, methods=['POST'])
def getMessage():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '!', 200

@app.route('/')
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + bot.token)
    return 'Webhook set!', 200

# Function to start polling (you can use this for local testing)
def safe_polling(bot, interval=0.25, timeout=20, long_polling_timeout=30):
    while True:
        try:
            bot.polling(non_stop=True, interval=interval, timeout=timeout, long_polling_timeout=long_polling_timeout)
        except Exception as e:
            logger.error(f'Error occurred: {e}')
            time.sleep(15)  # Wait for 15 seconds before retrying

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
    # safe_polling(bot)  # Uncomment this line if you want to use polling for local testing
