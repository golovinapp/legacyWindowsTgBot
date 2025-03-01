# rdp_sessions.py
import subprocess
import re

def get_sessions():
    result = subprocess.run("qwinsta", capture_output=True, text=True, shell=True, encoding='cp866')
    lines = result.stdout.splitlines()
    sessions = []
    
    pattern = r'^(.+?)\s+(\d+)\s+([^\s]+)(?:\s+rdpwd)?$'
    system_users = ['services', 'console', 'rdp-tcp']
    
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
            
        match = re.match(pattern, line)
        if match:
            user_full, session_id, state = match.groups()
            user_full = user_full.replace('>', '')
            
            user = user_full
            if user.startswith('rdp-tcp#'):
                parts = user.split(maxsplit=1)
                if len(parts) > 1:
                    user = parts[1].strip()
            
            if user.lower() in system_users:
                continue
            
            state_map = {
                "Диск": "Отключен",
                "Подключено": "Подключено",
                "Активен": "Активен",
                "Прием": "Прием",
                "Активно": "Активен"
            }
            state = state_map.get(state, state)
            
            sessions.append({"id": session_id, "user": user, "state": state})
    
    return sessions if sessions else []

def logoff_session(session_id):
    try:
        subprocess.run(f"logoff {session_id}", shell=True, check=True)
        return True, f"Сеанс с ID {session_id} завершён."
    except subprocess.CalledProcessError:
        return False, f"Ошибка: не удалось завершить сеанс с ID {session_id}."