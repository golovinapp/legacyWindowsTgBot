# user_management.py
import subprocess
import re
import chardet
import random
import string
from rdp_sessions import get_sessions, logoff_session

def generate_password():
    """
    Генерирует случайный пароль из 8 символов.
    Содержит заглавные и строчные буквы, цифры и специальные символы.
    Гарантированно содержит минимум 1 цифру.
    """
    # Определяем наборы символов
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase  
    digits = string.digits
    special = "!@#$%&*"
    
    # Гарантируем наличие каждого типа символов
    password = []
    password.append(random.choice(lowercase))   # минимум 1 строчная
    password.append(random.choice(uppercase))   # минимум 1 заглавная
    password.append(random.choice(digits))      # минимум 1 цифра
    password.append(random.choice(special))     # минимум 1 спецсимвол
    
    # Заполняем остальные 4 позиции случайными символами
    all_chars = lowercase + uppercase + digits + special
    for _ in range(4):
        password.append(random.choice(all_chars))
    
    # Перемешиваем символы для случайного порядка
    random.shuffle(password)
    
    return ''.join(password)

def change_user_password(username):
    """
    Меняет пароль пользователя на автоматически сгенерированный.
    Возвращает кортеж (успех: bool, сообщение: str, новый_пароль: str)
    """
    try:
        # Генерируем новый пароль
        new_password = generate_password()
        
        # Применяем тот же подход к именам что и в других функциях
        if " " in username:
            cmd = f'net user "{username}" "{new_password}"'
        else:
            cmd = f'net user {username} "{new_password}"'
            
        result = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = result.stdout or result.stderr
        
        # Применяем тот же подход декодирования что в других функциях
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)
        
        if detected_encoding and confidence > 0.5:
            decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_output = raw_bytes.decode("cp866", errors="replace")
        
        if result.returncode == 0:
            message = f"Пароль пользователя {username} успешно изменен"
            return True, message, new_password
        else:
            # Если основная команда не сработала, попробуем PowerShell как backup
            try:
                # Экранируем спецсимволы для PowerShell - упрощенная версия
                safe_password = new_password.replace('"', "'")  # заменяем двойные кавычки на одинарные
                ps_cmd = f'powershell -Command "Set-LocalUser -Name \\"{username}\\" -Password (ConvertTo-SecureString \\"{safe_password}\\" -AsPlainText -Force)"'
                ps_result = subprocess.run(ps_cmd, capture_output=True, shell=True)
                if ps_result.returncode == 0:
                    message = f"Пароль пользователя {username} успешно изменен (PowerShell)"
                    return True, message, new_password
                else:
                    return False, f"Ошибка смены пароля: {decoded_output}", ""
            except Exception:
                return False, f"Ошибка смены пароля: {decoded_output}", ""
            
    except Exception as e:
        return False, f"Исключение при смене пароля пользователя {username}: {str(e)}", ""

def get_users():
    """
    Получает список локальных пользователей системы.
    Возвращает список словарей с информацией о пользователях.
    """
    try:
        # Получаем список пользователей через wmic
        cmd = 'wmic useraccount where "LocalAccount=True" get Name,Disabled'
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout
        
        # Используем тот же подход что и в VPN модуле
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)
        
        # Если chardet уверенно определил кодировку, используем её;
        # иначе пробуем cp866 как самую распространённую для старых русских Windows.
        if detected_encoding and confidence > 0.5:
            decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_output = raw_bytes.decode("cp866", errors="replace")
        
        lines = [line.strip() for line in decoded_output.splitlines() if line.strip()]
        users = []
        
        if len(lines) > 1:
            # Пропускаем заголовок
            for line in lines[1:]:
                parts = line.split(None, 1)  # Разделяем только на 2 части: статус и полное имя
                if len(parts) >= 2:
                    disabled = parts[0].upper() == "TRUE"
                    full_name = parts[1].strip()  # Полное имя пользователя со всеми пробелами
                    
                    # Исключаем системные учетки
                    if full_name.lower() not in ['administrator', 'guest', 'defaultaccount', 'администратор', 'гость']:
                        users.append({
                            "name": full_name,  # Сохраняем полное имя!
                            "disabled": disabled,
                            "status": "Заблокирован" if disabled else "Активен"
                        })
        
        return users
    except Exception as e:
        print(f"Ошибка получения списка пользователей: {e}")
        return []

def block_user(username):
    """
    Блокирует пользователя:
    1. Проверяет активные RDP сессии и завершает их
    2. Блокирует учетную запись пользователя
    
    Возвращает кортеж (успех: bool, сообщение: str)
    """
    try:
        messages = []
        
        # 1. Проверяем активные RDP сессии пользователя
        sessions = get_sessions()
        user_sessions = [s for s in sessions if s['user'].lower() == username.lower()]
        
        if user_sessions:
            messages.append(f"Найдено активных сессий пользователя {username}: {len(user_sessions)}")
            
            # Завершаем все сессии пользователя
            for session in user_sessions:
                success, msg = logoff_session(session['id'])
                if success:
                    messages.append(f"Сессия {session['id']} завершена")
                else:
                    messages.append(f"Ошибка завершения сессии {session['id']}: {msg}")
        else:
            messages.append(f"Активных RDP сессий пользователя {username} не найдено")
        
        # 2. Блокируем учетную запись (используем подход как в VPN модуле)
        if " " in username:
            cmd = f'net user "{username}" /active:no'
        else:
            cmd = f"net user {username} /active:no"
            
        result = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = result.stdout or result.stderr
        
        # Применяем тот же подход декодирования что в VPN модуле
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)
        
        if detected_encoding and confidence > 0.5:
            decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_output = raw_bytes.decode("cp866", errors="replace")
        
        if result.returncode == 0:
            messages.append(f"Учетная запись {username} заблокирована")
            return True, "\n".join(messages)
        else:
            # Если основная команда не сработала, попробуем PowerShell как backup
            try:
                ps_cmd = f'powershell -Command "Disable-LocalUser -Name \\"{username}\\""'
                ps_result = subprocess.run(ps_cmd, capture_output=True, shell=True)
                if ps_result.returncode == 0:
                    messages.append(f"Учетная запись {username} заблокирована (PowerShell)")
                    return True, "\n".join(messages)
                else:
                    messages.append(f"Ошибка блокировки учетной записи: {decoded_output}")
                    return False, "\n".join(messages)
            except Exception:
                messages.append(f"Ошибка блокировки учетной записи: {decoded_output}")
                return False, "\n".join(messages)
            
    except Exception as e:
        return False, f"Исключение при блокировке пользователя {username}: {str(e)}"

def unblock_user(username):
    """
    Разблокирует пользователя.
    Возвращает кортеж (успех: bool, сообщение: str)
    """
    try:
        # Используем тот же подход что в VPN модуле
        if " " in username:
            cmd = f'net user "{username}" /active:yes'
        else:
            cmd = f"net user {username} /active:yes"
            
        result = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = result.stdout or result.stderr
        
        # Применяем тот же подход декодирования что в VPN модуле
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)
        
        if detected_encoding and confidence > 0.5:
            decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_output = raw_bytes.decode("cp866", errors="replace")
        
        if result.returncode == 0:
            return True, f"Учетная запись {username} разблокирована"
        else:
            # Если основная команда не сработала, попробуем PowerShell как backup
            try:
                ps_cmd = f'powershell -Command "Enable-LocalUser -Name \\"{username}\\""'
                ps_result = subprocess.run(ps_cmd, capture_output=True, shell=True)
                if ps_result.returncode == 0:
                    return True, f"Учетная запись {username} разблокирована (PowerShell)"
                else:
                    return False, f"Ошибка разблокировки учетной записи: {decoded_output}"
            except Exception:
                return False, f"Ошибка разблокировки учетной записи: {decoded_output}"
            
    except Exception as e:
        return False, f"Исключение при разблокировке пользователя {username}: {str(e)}"

def get_user_info(username):
    """
    Получает подробную информацию о пользователе.
    Возвращает словарь с информацией или None при ошибке.
    """
    try:
        cmd = f'net user "{username}"'
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout
        
        # Применяем тот же подход декодирования что в VPN модуле
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)
        
        # Если chardet уверенно определил кодировку, используем её;
        # иначе пробуем cp866 как самую распространённую для старых русских Windows.
        if detected_encoding and confidence > 0.5:
            decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_output = raw_bytes.decode("cp866", errors="replace")
        
        if proc.returncode != 0:
            return None
            
        # Ищем статус учетной записи
        active_match = re.search(r"Учетная запись активна\s+(.+)", decoded_output, re.IGNORECASE)
        if not active_match:
            active_match = re.search(r"Account active\s+(.+)", decoded_output, re.IGNORECASE)
            
        last_logon_match = re.search(r"Последний вход\s+(.+)", decoded_output, re.IGNORECASE)
        if not last_logon_match:
            last_logon_match = re.search(r"Last logon\s+(.+)", decoded_output, re.IGNORECASE)
        
        return {
            "name": username,
            "active": active_match.group(1).strip() if active_match else "Неизвестно",
            "last_logon": last_logon_match.group(1).strip() if last_logon_match else "Неизвестно"
        }
        
    except Exception as e:
        print(f"Ошибка получения информации о пользователе {username}: {e}")
        return None