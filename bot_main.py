import sys
import ctypes
import os
import telegram
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters,
                          CallbackQueryHandler, CallbackContext, ConversationHandler)
import re
from dotenv import load_dotenv

from system_info import get_server_load
from rdp_sessions import get_sessions, logoff_session
from vpn_connections import get_vpn_sessions, reset_vpn_session
from server_control import reboot_server, restart_vpn_service
from network_check import check_speedtest, check_network_status, check_custom_connection
from user_management import get_users, block_user, unblock_user, get_user_info, change_user_password
from backup_monitoring import get_backup_status, get_backup_versions, start_manual_backup, check_backup_disk_space

# Загружаем переменные из .env файла
load_dotenv()

# Получаем конфигурацию из переменных окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USERS_STR = os.getenv("ALLOWED_USERS", "")

# Обработка списка разрешенных пользователей
if ALLOWED_USERS_STR:
    ALLOWED_USERS = [int(user_id.strip()) for user_id in ALLOWED_USERS_STR.split(",") if user_id.strip().isdigit()]
else:
    ALLOWED_USERS = []

# Проверяем, что необходимые переменные загружены
if not TOKEN:
    print("❌ Ошибка: TELEGRAM_TOKEN не найден в .env файле!")
    print("Создайте файл .env и добавьте в него:")
    print("TELEGRAM_TOKEN=your_bot_token_here")
    sys.exit(1)

if not ALLOWED_USERS:
    print("❌ Предупреждение: ALLOWED_USERS не настроен в .env файле!")
    print("Добавьте в .env файл:")
    print("ALLOWED_USERS=123456,654321")
    sys.exit(1)

print(f"✅ Конфигурация загружена:")
print(f"   - Токен бота: {'*' * (len(TOKEN)-8) + TOKEN[-8:] if TOKEN else 'не задан'}")
print(f"   - Разрешенных пользователей: {len(ALLOWED_USERS)}")

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
        [telegram.KeyboardButton("Управление пользователями")],
        [telegram.KeyboardButton("Управление сервером")],
        [telegram.KeyboardButton("VPN соединения")],
        [telegram.KeyboardButton("Проверка связи")],
        [telegram.KeyboardButton("Резервные копии")]
    ]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    update.message.reply_text("Привет! Я помогу управлять сеансами, мониторить сервер, VPN и резервные копии. Выбери действие:", reply_markup=reply_markup)

def handle_message(update: telegram.Update, context: CallbackContext):
    if not is_authorized(update):
        update.message.reply_text("У вас нет доступа к управлению ботом.")
        return

    text = update.message.text
    if text == "Состояние сервера":
        show_server_load(update, context)
    elif text == "VPN соединения":
        show_vpn_sessions(update, context)
    elif text == "Управление пользователями":
        show_user_management_menu(update, context)
    elif text == "Управление сервером":
        show_server_control_menu(update, context)
    elif text == "Проверка связи":
        show_network_menu(update, context)
    elif text == "Резервные копии":
        show_backup_menu(update, context)
    elif text == "Список пользователей":
        show_users_list(update, context)
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
    elif text == "Статус резервных копий":
        do_show_backup_status(update, context)
    elif text == "Список версий копий":
        do_show_backup_versions(update, context)
    elif text == "Место на дисках":
        do_check_backup_disk_space(update, context)
    elif text == "Назад":
        start(update, context)
    else:
        update.message.reply_text("Неизвестная команда.")
    return ConversationHandler.END

# ============== НОВЫЕ ФУНКЦИИ ДЛЯ РЕЗЕРВНОГО КОПИРОВАНИЯ ==============

def show_backup_menu(update: telegram.Update, context: CallbackContext):
    """Показывает меню управления резервными копиями"""
    keyboard = [
        [telegram.KeyboardButton("Статус резервных копий")],
        [telegram.KeyboardButton("Список версий копий")],
        [telegram.KeyboardButton("Место на дисках")],
        [telegram.KeyboardButton("Назад")]
    ]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    update.message.reply_text("📁 Управление резервными копиями:", reply_markup=reply_markup)

def do_show_backup_status(update: telegram.Update, context: CallbackContext):
    """Показывает статус резервных копий с дополнительными действиями"""
    update.message.reply_text("⏳ Проверяю статус резервных копий...")
    status_info = get_backup_status()
    
    # Создаем inline кнопки для дополнительных действий
    keyboard = [
        [telegram.InlineKeyboardButton("🔄 Обновить статус", callback_data="refresh_backup_status")],
        [telegram.InlineKeyboardButton("📋 Детали", callback_data="backup_details")]
    ]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(status_info, reply_markup=reply_markup)

def do_show_backup_versions(update: telegram.Update, context: CallbackContext):
    """Показывает список версий резервных копий"""
    update.message.reply_text("⏳ Получаю список версий копий...")
    versions_info = get_backup_versions()
    
    keyboard = [
        [telegram.InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_backup_versions")]
    ]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(versions_info, reply_markup=reply_markup)

def do_check_backup_disk_space(update: telegram.Update, context: CallbackContext):
    """Проверяет место на дисках для резервных копий"""
    update.message.reply_text("⏳ Проверяю место на дисках...")
    disk_info = check_backup_disk_space()
    
    keyboard = [
        [telegram.InlineKeyboardButton("🔄 Обновить информацию", callback_data="refresh_disk_space")]
    ]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(disk_info, reply_markup=reply_markup)

# ============== ОБРАБОТЧИКИ CALLBACK ДЛЯ РЕЗЕРВНОГО КОПИРОВАНИЯ ==============

def handle_refresh_backup_status(update: telegram.Update, context: CallbackContext):
    """Обновляет статус резервных копий"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer("🔄 Обновляю статус...")
    
    status_info = get_backup_status()
    
    # Убрали кнопку "Ручной запуск"
    keyboard = [
        [telegram.InlineKeyboardButton("🔄 Обновить статус", callback_data="refresh_backup_status")],
        [telegram.InlineKeyboardButton("📋 Детали", callback_data="backup_details")]
    ]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(status_info, reply_markup=reply_markup)

def handle_manual_backup(update: telegram.Update, context: CallbackContext):
    """Обрабатывает запрос ручного запуска резервного копирования"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer()
    
    query.edit_message_text("⏳ Проверяю возможность ручного запуска резервного копирования...")
    
    success, message = start_manual_backup()
    
    keyboard = [
        [telegram.InlineKeyboardButton("◀️ Назад к статусу", callback_data="refresh_backup_status")]
    ]
    
    if success:
        keyboard.insert(0, [telegram.InlineKeyboardButton("⚠️ ВНИМАНИЕ: Подтвердить запуск", callback_data="confirm_manual_backup")])
    
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    if success:
        final_message = f"✅ {message}\n\n⚠️ ВНИМАНИЕ: Ручное резервное копирование может занять длительное время и повлиять на производительность сервера!"
    else:
        final_message = f"❌ {message}"
    
    query.edit_message_text(final_message, reply_markup=reply_markup)

def handle_confirm_manual_backup(update: telegram.Update, context: CallbackContext):
    """Подтверждение ручного запуска резервного копирования"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer()
    
    # В производственной среде здесь можно добавить реальный запуск резервного копирования
    # Пока просто информируем пользователя
    message = ("⚠️ Функция ручного запуска резервного копирования отключена в целях безопасности.\n\n"
               "Для запуска резервного копирования:\n"
               "1. Подключитесь к серверу через RDP\n"
               "2. Откройте Windows Server Backup\n"
               "3. Выберите 'Архивировать однократно'\n\n"
               "Или обратитесь к системному администратору.")
    
    keyboard = [
        [telegram.InlineKeyboardButton("◀️ Назад к статусу", callback_data="refresh_backup_status")]
    ]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(message, reply_markup=reply_markup)

def handle_backup_details(update: telegram.Update, context: CallbackContext):
    """Показывает детальную информацию о резервных копиях"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer("📋 Получаю детальную информацию...")
    
    # Получаем подробную информацию
    versions_info = get_backup_versions()
    disk_info = check_backup_disk_space()
    
    detailed_info = f"📋 Детальная информация о резервных копиях:\n\n{versions_info}\n\n{disk_info}"
    
    keyboard = [
        [telegram.InlineKeyboardButton("🔄 Обновить", callback_data="backup_details")],
        [telegram.InlineKeyboardButton("◀️ Назад к статусу", callback_data="refresh_backup_status")]
    ]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(detailed_info, reply_markup=reply_markup)

def handle_refresh_backup_versions(update: telegram.Update, context: CallbackContext):
    """Обновляет список версий резервных копий"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer("🔄 Обновляю список...")
    
    versions_info = get_backup_versions()
    
    keyboard = [
        [telegram.InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_backup_versions")]
    ]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(versions_info, reply_markup=reply_markup)

def handle_refresh_disk_space(update: telegram.Update, context: CallbackContext):
    """Обновляет информацию о месте на дисках"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer("🔄 Обновляю информацию...")
    
    disk_info = check_backup_disk_space()
    
    keyboard = [
        [telegram.InlineKeyboardButton("🔄 Обновить информацию", callback_data="refresh_disk_space")]
    ]
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(disk_info, reply_markup=reply_markup)

# ============== ОСТАЛЬНЫЕ ФУНКЦИИ (ОРИГИНАЛЬНЫЕ) ==============

def show_user_management_menu(update: telegram.Update, context: CallbackContext):
    """Показывает меню управления пользователями"""
    keyboard = [
        [telegram.KeyboardButton("Список пользователей")],
        [telegram.KeyboardButton("Назад")]
    ]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    update.message.reply_text("Выберите действие для управления пользователями:", reply_markup=reply_markup)

def show_users_list(update: telegram.Update, context: CallbackContext):
    """Показывает список пользователей в виде кнопок"""
    update.message.reply_text("Получаю список пользователей...")
    users = get_users()
    
    if not users:
        update.message.reply_text("Пользователи не найдены или произошла ошибка.")
        return

    keyboard = []
    
    for user in users:
        if user['disabled']:
            button_text = f"🔴 {user['name']} (Заблокирован)"
        else:
            button_text = f"🟢 {user['name']} (Активен)"
            
        callback_data = f"user_menu_{user['name']}"
        keyboard.append([telegram.InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([telegram.InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_users")])
    
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    update.message.reply_text("👥 Пользователи системы:", reply_markup=reply_markup)

def handle_user_menu(update: telegram.Update, context: CallbackContext):
    """Показывает меню действий для конкретного пользователя"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer()
    
    username = query.data.replace("user_menu_", "")
    
    # Получаем актуальную информацию о пользователе
    users = get_users()
    user_info = next((u for u in users if u['name'] == username), None)
    
    if not user_info:
        query.edit_message_text("❌ Пользователь не найден")
        return
    
    status_emoji = "🔴" if user_info['disabled'] else "🟢"
    status_text = "Заблокирован" if user_info['disabled'] else "Активен"
    
    keyboard = []
    
    if user_info['disabled']:
        keyboard.append([telegram.InlineKeyboardButton("🔓 Разблокировать", callback_data=f"unblock_{username}")])
    else:
        keyboard.append([telegram.InlineKeyboardButton("🔒 Заблокировать", callback_data=f"block_{username}")])
    
    keyboard.append([telegram.InlineKeyboardButton("ℹ️ Подробная информация", callback_data=f"info_{username}")])
    keyboard.append([telegram.InlineKeyboardButton("👀 Активные сессии", callback_data=f"sessions_{username}")])
    keyboard.append([telegram.InlineKeyboardButton("🔑 Сменить пароль", callback_data=f"changepass_{username}")])
    keyboard.append([telegram.InlineKeyboardButton("◀️ Назад к списку", callback_data="back_to_users")])
    
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    message_text = (f"👤 Управление пользователем\n\n"
                   f"🏷️ Имя: {username}\n"
                   f"📊 Статус: {status_emoji} {status_text}")
    
    query.edit_message_text(message_text, reply_markup=reply_markup)

def handle_user_sessions(update: telegram.Update, context: CallbackContext):
    """Показывает активные сессии пользователя"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer()
    
    username = query.data.replace("sessions_", "")
    
    sessions = get_sessions()
    user_sessions = [s for s in sessions if s['user'].lower() == username.lower()]
    
    if not user_sessions:
        sessions_text = f"У пользователя {username} нет активных RDP сессий"
    else:
        sessions_lines = [f"🖥️ Активные RDP сессии пользователя {username}:"]
        for session in user_sessions:
            sessions_lines.append(f"• ID: {session['id']}, Состояние: {session['state']}")
        sessions_text = "\n".join(sessions_lines)
    
    keyboard = [
        [telegram.InlineKeyboardButton("◀️ Назад", callback_data=f"user_menu_{username}")]
    ]
    
    if user_sessions:
        for session in user_sessions:
            keyboard.insert(-1, [telegram.InlineKeyboardButton(
                f"❌ Завершить сессию {session['id']}", 
                callback_data=f"logoff_{session['id']}"
            )])
    
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    query.edit_message_text(sessions_text, reply_markup=reply_markup)

def handle_back_to_users(update: telegram.Update, context: CallbackContext):
    """Возвращает к списку пользователей"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer()
    
    users = get_users()
    
    if not users:
        query.edit_message_text("Пользователи не найдены или произошла ошибка.")
        return

    keyboard = []
    
    for user in users:
        if user['disabled']:
            button_text = f"🔴 {user['name']} (Заблокирован)"
        else:
            button_text = f"🟢 {user['name']} (Активен)"
            
        callback_data = f"user_menu_{user['name']}"
        keyboard.append([telegram.InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([telegram.InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_users")])
    
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    query.edit_message_text("👥 Пользователи системы:", reply_markup=reply_markup)

def handle_refresh_users(update: telegram.Update, context: CallbackContext):
    """Обновляет список пользователей"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer("🔄 Обновляю список...")
    
    handle_back_to_users(update, context)

def handle_change_password(update: telegram.Update, context: CallbackContext):
    """Обрабатывает смену пароля пользователя"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
    query = update.callback_query
    query.answer()
    callback_data = query.data
    
    if callback_data.startswith("changepass_"):
        username = callback_data.replace("changepass_", "")
        query.edit_message_text(f"⏳ Генерирую новый пароль для пользователя {username}...")
        
        success, message, new_password = change_user_password(username)
        
        keyboard = [[telegram.InlineKeyboardButton("◀️ Назад к пользователю", callback_data=f"user_menu_{username}")],
                   [telegram.InlineKeyboardButton("📋 К списку пользователей", callback_data="back_to_users")]]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        
        if success:
            # Экранируем специальные символы для HTML
            escaped_password = (new_password
                              .replace('&', '&amp;')
                              .replace('<', '&lt;')
                              .replace('>', '&gt;'))
            
            final_message = (f"✅ {message}\n\n"
                           f"🔑 Новый пароль: <code>{escaped_password}</code>\n\n"
                           f"⚠️ ВАЖНО: Сохраните этот пароль в надежном месте! "
                           f"Пароль показывается только один раз.")
            
            query.edit_message_text(final_message, reply_markup=reply_markup, parse_mode='HTML')
        else:
            final_message = f"❌ Ошибка смены пароля пользователя {username}:\n\n{message}"
            query.edit_message_text(final_message, reply_markup=reply_markup)

# ============== VPN ФУНКЦИИ В ЕДИНОМ СТИЛЕ ==============

def show_vpn_sessions(update: telegram.Update, context: CallbackContext):
    """Показывает список VPN-соединений в виде кнопок (единый стиль с пользователями)"""
    update.message.reply_text("Получаю список VPN-соединений...")
    vpn_sessions = get_vpn_sessions()
    
    if not vpn_sessions:
        update.message.reply_text("Нет активных VPN-соединений.")
        return

    keyboard = []
    
    for session in vpn_sessions:
        button_text = f"🌐 {session['name']} ({session['connect_time']})"
        callback_data = f"vpn_menu_{session['name']}"
        keyboard.append([telegram.InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([telegram.InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_vpn")])
    
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    update.message.reply_text("🌐 VPN-соединения:", reply_markup=reply_markup)

def handle_vpn_menu(update: telegram.Update, context: CallbackContext):
    """Показывает меню действий для конкретного VPN-соединения"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer()
    
    vpn_name = query.data.replace("vpn_menu_", "")
    
    # Получаем актуальную информацию о VPN сессии
    vpn_sessions = get_vpn_sessions()
    vpn_info = next((s for s in vpn_sessions if s['name'] == vpn_name), None)
    
    if not vpn_info:
        query.edit_message_text("❌ VPN-соединение не найдено")
        return
    
    keyboard = []
    keyboard.append([telegram.InlineKeyboardButton("🔌 Сбросить соединение", callback_data=f"reset_vpn_{vpn_name}")])
    keyboard.append([telegram.InlineKeyboardButton("◀️ Назад к списку", callback_data="back_to_vpn")])
    
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    
    message_text = (f"🌐 Управление VPN-соединением\n\n"
                   f"👤 Пользователь: {vpn_name}\n"
                   f"⏱️ Время подключения: {vpn_info['connect_time']}")
    
    query.edit_message_text(message_text, reply_markup=reply_markup)

def handle_back_to_vpn(update: telegram.Update, context: CallbackContext):
    """Возвращает к списку VPN-соединений"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer()
    
    vpn_sessions = get_vpn_sessions()
    
    if not vpn_sessions:
        query.edit_message_text("Нет активных VPN-соединений.")
        return

    keyboard = []
    
    for session in vpn_sessions:
        button_text = f"🌐 {session['name']} ({session['connect_time']})"
        callback_data = f"vpn_menu_{session['name']}"
        keyboard.append([telegram.InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([telegram.InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_vpn")])
    
    reply_markup = telegram.InlineKeyboardMarkup(keyboard)
    query.edit_message_text("🌐 VPN-соединения:", reply_markup=reply_markup)

def handle_refresh_vpn(update: telegram.Update, context: CallbackContext):
    """Обновляет список VPN-соединений"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
        
    query = update.callback_query
    query.answer("🔄 Обновляю список...")
    
    handle_back_to_vpn(update, context)

def handle_reset_vpn(update: telegram.Update, context: CallbackContext):
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
    query = update.callback_query
    query.answer()
    callback_data = query.data
    if callback_data.startswith("reset_vpn_"):
        user_name = callback_data.replace("reset_vpn_", "")
        query.edit_message_text(f"⏳ Сбрасываю VPN-соединение {user_name}...")
        success, message = reset_vpn_session(user_name)
        
        # Добавляем навигацию в едином стиле
        keyboard = [[telegram.InlineKeyboardButton("◀️ Назад к VPN соединениям", callback_data="back_to_vpn")]]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        
        if success:
            final_message = f"✅ {message}"
        else:
            final_message = f"❌ {message}"
            
        query.edit_message_text(final_message, reply_markup=reply_markup)

# ============== ОСТАЛЬНЫЕ ФУНКЦИИ ==============

def show_server_control_menu(update: telegram.Update, context: CallbackContext):
    keyboard = [
        [telegram.KeyboardButton("Состояние сервера")],
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

def handle_block_user(update: telegram.Update, context: CallbackContext):
    """Обрабатывает блокировку пользователя"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
    query = update.callback_query
    query.answer()
    callback_data = query.data
    
    if callback_data.startswith("block_"):
        username = callback_data.replace("block_", "")
        query.edit_message_text(f"⏳ Блокирую пользователя {username}...")
        success, message = block_user(username)
        
        keyboard = [[telegram.InlineKeyboardButton("◀️ Назад к пользователю", callback_data=f"user_menu_{username}")],
                   [telegram.InlineKeyboardButton("📋 К списку пользователей", callback_data="back_to_users")]]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        
        if success:
            final_message = f"✅ Пользователь {username} заблокирован:\n\n{message}"
        else:
            final_message = f"❌ Ошибка блокировки пользователя {username}:\n\n{message}"
            
        query.edit_message_text(final_message, reply_markup=reply_markup)

def handle_unblock_user(update: telegram.Update, context: CallbackContext):
    """Обрабатывает разблокировку пользователя"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
    query = update.callback_query
    query.answer()
    callback_data = query.data
    
    if callback_data.startswith("unblock_"):
        username = callback_data.replace("unblock_", "")
        query.edit_message_text(f"⏳ Разблокирую пользователя {username}...")
        success, message = unblock_user(username)
        
        keyboard = [[telegram.InlineKeyboardButton("◀️ Назад к пользователю", callback_data=f"user_menu_{username}")],
                   [telegram.InlineKeyboardButton("📋 К списку пользователей", callback_data="back_to_users")]]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        
        if success:
            final_message = f"✅ {message}"
        else:
            final_message = f"❌ {message}"
            
        query.edit_message_text(final_message, reply_markup=reply_markup)

def handle_user_info(update: telegram.Update, context: CallbackContext):
    """Показывает подробную информацию о пользователе"""
    if not is_authorized(update):
        update.callback_query.answer("У вас нет доступа.", show_alert=True)
        return
    query = update.callback_query
    query.answer()
    callback_data = query.data
    
    if callback_data.startswith("info_"):
        username = callback_data.replace("info_", "")
        query.edit_message_text(f"⏳ Получаю информацию о пользователе {username}...")
        
        user_info = get_user_info(username)
        keyboard = [[telegram.InlineKeyboardButton("◀️ Назад", callback_data=f"user_menu_{username}")]]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        
        if user_info:
            info_text = (f"👤 Информация о пользователе {username}:\n\n"
                        f"📊 Статус: {user_info['active']}\n"
                        f"🕒 Последний вход: {user_info['last_logon']}")
        else:
            info_text = f"❌ Не удалось получить информацию о пользователе {username}"
            
        query.edit_message_text(info_text, reply_markup=reply_markup)

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
    dp.add_handler(CallbackQueryHandler(handle_block_user, pattern=r'^block_'))
    dp.add_handler(CallbackQueryHandler(handle_unblock_user, pattern=r'^unblock_'))
    dp.add_handler(CallbackQueryHandler(handle_user_info, pattern=r'^info_'))
    dp.add_handler(CallbackQueryHandler(handle_change_password, pattern=r'^changepass_'))
    dp.add_handler(CallbackQueryHandler(handle_user_menu, pattern=r'^user_menu_'))
    dp.add_handler(CallbackQueryHandler(handle_user_sessions, pattern=r'^sessions_'))
    dp.add_handler(CallbackQueryHandler(handle_back_to_users, pattern=r'^back_to_users'))
    dp.add_handler(CallbackQueryHandler(handle_refresh_users, pattern=r'^refresh_users'))
    # VPN обработчики в едином стиле
    dp.add_handler(CallbackQueryHandler(handle_vpn_menu, pattern=r'^vpn_menu_'))
    dp.add_handler(CallbackQueryHandler(handle_back_to_vpn, pattern=r'^back_to_vpn'))
    dp.add_handler(CallbackQueryHandler(handle_refresh_vpn, pattern=r'^refresh_vpn'))
    # НОВЫЕ обработчики для резервного копирования (убрали manual_backup)
    dp.add_handler(CallbackQueryHandler(handle_refresh_backup_status, pattern=r'^refresh_backup_status'))
    dp.add_handler(CallbackQueryHandler(handle_backup_details, pattern=r'^backup_details'))
    dp.add_handler(CallbackQueryHandler(handle_refresh_backup_versions, pattern=r'^refresh_backup_versions'))
    dp.add_handler(CallbackQueryHandler(handle_refresh_disk_space, pattern=r'^refresh_disk_space'))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()