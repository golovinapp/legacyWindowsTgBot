import sys
import ctypes
import telegram
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters,
                          CallbackQueryHandler, CallbackContext, ConversationHandler)
import re

from system_info import get_server_load
from rdp_sessions import get_sessions, logoff_session
from vpn_connections import get_vpn_sessions, reset_vpn_session
from server_control import reboot_server, restart_vpn_service
from network_check import check_speedtest, check_network_status, check_custom_connection

# Указываем токен бота прямо в коде
TOKEN = "token"

# Список Telegram ID, с которых разрешено управление ботом
ALLOWED_USERS = [123456, 654321]  # замените на реальные ID

# Константа для состояния ввода адреса для проверки связи до узла
CHECK_HOST = range(1)

def is_authorized(update: telegram.Update) -> bool:
    user_id = update.effective_user.id
    return user_id in ALLOWED_USERS

def check_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception as e:
        print(f"Ошибка проверки прав администратора: {e}")
        return False

def start(update: telegram.Update, context: CallbackContext):
    if not is_authorized(update):
        update.message.reply_text("У вас нет доступа к управлению ботом.")
        return

    keyboard = [
        [telegram.KeyboardButton("Активные пользователи")],
        [telegram.KeyboardButton("Загрузка сервера")],
        [telegram.KeyboardButton("VPN соединения")],
        [telegram.KeyboardButton("Управление сервером")],
        [telegram.KeyboardButton("Проверка связи")]
    ]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    update.message.reply_text("Привет! Я помогу управлять сеансами, мониторить сервер и VPN. Выбери действие:", reply_markup=reply_markup)

def handle_message(update: telegram.Update, context: CallbackContext):
    if not is_authorized(update):
        update.message.reply_text("У вас нет доступа к управлению ботом.")
        return

    text = update.message.text
    if text == "Активные пользователи":
        show_sessions(update, context)
    elif text == "Загрузка сервера":
        show_server_load(update, context)
    elif text == "VPN соединения":
        show_vpn_sessions(update, context)
    elif text == "Управление сервером":
        show_server_control_menu(update, context)
    elif text == "Проверка связи":
        show_network_menu(update, context)
    elif text == "Перезагрузка сервера":
        do_reboot_server(update, context)
    elif text == "Перезапуск VPN":
        do_restart_vpn(update, context)
    elif text == "Проверить скорость":
        do_check_speedtest(update, context)
    elif text == "Состояние сети":
        do_check_network_status(update, context)
    elif text == "Проверить связь до узла":
        update.message.reply_text("Введите IP или доменное имя:")
        return CHECK_HOST
    elif text == "Назад":
        start(update, context)
    else:
        update.message.reply_text("Неизвестная команда.")
    return ConversationHandler.END

def show_server_control_menu(update: telegram.Update, context: CallbackContext):
    keyboard = [
        [telegram.KeyboardButton("Перезагрузка сервера")],
        [telegram.KeyboardButton("Перезапуск VPN")],
        [telegram.KeyboardButton("Назад")]
    ]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

def do_reboot_server(update: telegram.Update, context: CallbackContext):
    success, message = reboot_server()
    update.message.reply_text(message)

def do_restart_vpn(update: telegram.Update, context: CallbackContext):
    success, message = restart_vpn_service()
    update.message.reply_text(message)

def show_sessions(update: telegram.Update, context: CallbackContext):
    sessions = get_sessions()
    if not sessions:
        update.message.reply_text("Нет активных или отключённых сеансов пользователей.")
        return

    keyboard = []
    for session in sessions:
        # Добавляем "Отключить" перед именем для ясности
        button_text = f"Отключить {session['user']} (ID: {session['id']})"
        keyboard.append([telegram.InlineKeyboardButton(button_text, callback_data=f"logoff_{session['id']}")])
    
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    response = "Активные сеансы:\n" + "\n".join(
        [f"ID: {s['id']}, Пользователь: {s['user']}, Состояние: {s['state']}" for s in sessions]
    )
    update.message.reply_text(response, reply_markup=reply_markup)

def show_server_load(update: telegram.Update, context: CallbackContext):
    update.message.reply_text("Собираю данные...")
    load_info = get_server_load()
    update.message.reply_text(load_info)

def show_vpn_sessions(update: telegram.Update, context: CallbackContext):
    vpn_sessions = get_vpn_sessions()
    if not vpn_sessions:
        update.message.reply_text("Нет активных VPN-соединений.")
        return

    keyboard = []
    for session in vpn_sessions:
        button_text = f"{session['name']} (Время: {session['connect_time']})"
        keyboard.append([telegram.InlineKeyboardButton(
            f"Сбросить {button_text}", callback_data=f"reset_vpn_{session['name']}"
        )])
    
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    response = "VPN-соединения:\n" + "\n".join(
        [f"Имя: {s['name']}, Время: {s['connect_time']}" for s in vpn_sessions]
    )
    update.message.reply_text(response, reply_markup=reply_markup)

def show_network_menu(update: telegram.Update, context: CallbackContext):
    keyboard = [
        [telegram.KeyboardButton("Проверить скорость")],
        [telegram.KeyboardButton("Состояние сети")],
        [telegram.KeyboardButton("Проверить связь до узла")],
        [telegram.KeyboardButton("Назад")]
    ]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

def do_check_speedtest(update: telegram.Update, context: CallbackContext):
    update.message.reply_text("Выполняю speedtest, подождите...")
    success, msg = check_speedtest()
    update.message.reply_text(msg)

def do_check_network_status(update: telegram.Update, context: CallbackContext):
    update.message.reply_text("Выполняю проверку сети, подождите...")
    success, msg = check_network_status()
    update.message.reply_text(msg)

def check_host_input(update: telegram.Update, context: CallbackContext):
    target = update.message.text.strip()
    update.message.reply_text(f"Выполняю проверку связи до {target}...")
    success, result_msg = check_custom_connection(target)
    update.message.reply_text(result_msg)
    return ConversationHandler.END

def cancel_check_host(update: telegram.Update, context: CallbackContext):
    update.message.reply_text("Отмена ввода адреса.")
    return ConversationHandler.END

def handle_logoff(update: telegram.Update, context: CallbackContext):
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
    query = update.callback_query
    query.answer()
    callback_data = query.data
    if callback_data.startswith("logoff_"):
        session_id = callback_data.replace("logoff_", "")
        success, message = logoff_session(session_id)
        query.edit_message_text(message)

def handle_reset_vpn(update: telegram.Update, context: CallbackContext):
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
    query = update.callback_query
    query.answer()
    callback_data = query.data
    if callback_data.startswith("reset_vpn_"):
        user_name = callback_data.replace("reset_vpn_", "")
        success, message = reset_vpn_session(user_name)
        query.edit_message_text(message)

def main():
    if not check_admin():
        print("Скрипт НЕ запущен с правами администратора!")
        sys.exit(1)
    else:
        print("Скрипт запущен с правами администратора.")

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # ConversationHandler для ввода адреса в разделе "Проверить связь до узла"
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.text("Проверить связь до узла"), handle_message)],
        states={
            CHECK_HOST: [MessageHandler(Filters.text & ~Filters.command, check_host_input)]
        },
        fallbacks=[MessageHandler(Filters.text("Отмена"), cancel_check_host)]
    )
    dp.add_handler(conv_handler)

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CallbackQueryHandler(handle_logoff, pattern=r'^logoff_'))
    dp.add_handler(CallbackQueryHandler(handle_reset_vpn, pattern=r'^reset_vpn_'))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
