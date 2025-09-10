# backup_monitoring.py
import subprocess
import re
import chardet
from datetime import datetime, timedelta
import os

def get_backup_status():
    """
    Получает общую информацию о состоянии резервных копий:
    - Статус последней резервной копии
    - Расписание резервного копирования
    - Место хранения
    Возвращает отформатированную строку с информацией.
    """
    try:
        status_lines = []
        
        # 1. Получаем информацию о последних резервных копиях
        last_backup_info = _get_last_backup_info()
        status_lines.append("📁 Состояние резервных копий:")
        status_lines.append(f"- Последняя копия: {last_backup_info}")
        
        # 2. Проверяем расписание
        schedule_info = _get_backup_schedule()
        status_lines.append(f"- Расписание: {schedule_info}")
        
        # 3. Проверяем место хранения (только если удается определить)
        storage_info = _get_storage_info()
        status_lines.extend(storage_info)
        
        return "\n".join(status_lines)
        
    except Exception as e:
        return f"❌ Ошибка получения данных о резервных копиях: {str(e)}"

def get_backup_versions():
    """
    Получает детальный список версий резервных копий.
    Возвращает отформатированную строку со списком копий.
    """
    try:
        cmd = "wbadmin get versions"
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout
        
        # Применяем тот же подход декодирования что в user_management.py
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)
        
        if detected_encoding and confidence > 0.5:
            decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_output = raw_bytes.decode("cp866", errors="replace")
        
        if proc.returncode != 0:
            return "❌ Не удалось получить список версий резервных копий. Возможно, Windows Server Backup не настроен."
        
        lines = []
        lines.append("📋 Список резервных копий:")
        
        # Парсим вывод wbadmin get versions для русской локализации
        backup_entries = _parse_backup_versions_ru(decoded_output)
        
        if not backup_entries:
            lines.append("🔍 Резервные копии не найдены")
        else:
            for entry in backup_entries[-5:]:  # Показываем последние 5 копий
                lines.append(f"• {entry}")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"❌ Ошибка получения версий резервных копий: {str(e)}"

def start_manual_backup():
    """
    ВНИМАНИЕ: Эта функция потенциально может запустить ручное резервное копирование.
    В текущей реализации только проверяет возможность запуска.
    """
    try:
        # Сначала проверяем, настроено ли резервное копирование
        cmd = "wbadmin get schedule"
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        
        if proc.returncode != 0:
            return False, "❌ Резервное копирование не настроено. Сначала необходимо настроить Windows Server Backup."
        
        # Проверяем, не выполняется ли уже резервное копирование
        current_status = _get_current_backup_status()
        if "выполняется" in current_status.lower() or "running" in current_status.lower():
            return False, "⚠️ Резервное копирование уже выполняется"
        
        # В производственной среде здесь можно добавить реальный запуск:
        # cmd = "wbadmin start backup -backupTarget:E: -include:C: -quiet"
        # Но для безопасности пока только информируем
        
        return True, "ℹ️ Ручной запуск резервного копирования доступен. Для фактического запуска обратитесь к системному администратору."
        
    except Exception as e:
        return False, f"❌ Ошибка при проверке возможности ручного резервного копирования: {str(e)}"

def check_backup_disk_space():
    """
    Проверяет свободное место на дисках, используемых для резервного копирования.
    """
    try:
        lines = []
        lines.append("💾 Место для резервных копий:")
        
        # Получаем информацию о целевых дисках
        target_drives = _get_backup_target_drives()
        
        if not target_drives:
            lines.append("⚠️ Целевые диски для резервного копирования не определены")
            return "\n".join(lines)
        
        # Проверяем свободное место на каждом диске
        for drive in target_drives:
            space_info = _get_drive_space(drive)
            lines.append(f"- Диск {drive}: {space_info}")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"❌ Ошибка проверки места на дисках: {str(e)}"

# ============== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==============

def _get_last_backup_info():
    """Получает информацию о последней резервной копии"""
    try:
        cmd = "wbadmin get versions"
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout
        
        # Применяем тот же подход декодирования что в VPN модуле
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)
        
        if detected_encoding and confidence > 0.5:
            decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_output = raw_bytes.decode("cp866", errors="replace")
        
        if proc.returncode != 0:
            return "❌ Не настроено"
        
        # Ищем последнюю копию - улучшенный парсинг для русской локализации
        lines = [line.strip() for line in decoded_output.splitlines() if line.strip()]
        
        # Ищем строки с датой и временем в различных форматах
        date_patterns = [
            r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})',  # 09.09.2025 23:00
            r'(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})',    # 09/09/2025 23:00
            r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})',    # 2025-09-09 23:00
        ]
        
        latest_date = None
        latest_time = None
        latest_status = None
        
        for line in lines:
            for pattern in date_patterns:
                match = re.search(pattern, line)
                if match:
                    date_str = match.group(1)
                    time_str = match.group(2)
                    
                    try:
                        # Пытаемся разобрать дату в разных форматах
                        if '.' in date_str:
                            backup_datetime = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
                        elif '/' in date_str:
                            backup_datetime = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
                        else:
                            backup_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                        
                        if latest_date is None or backup_datetime > latest_date:
                            latest_date = backup_datetime
                            latest_time = time_str
                            
                            # Ищем статус в той же строке или следующих
                            if "успех" in line.lower():
                                latest_status = "✅"
                            elif "ошибка" in line.lower() or "неудач" in line.lower():
                                latest_status = "❌"
                            
                    except ValueError:
                        continue
        
        if latest_date:
            time_diff = datetime.now() - latest_date
            status_indicator = latest_status if latest_status else ""
            
            if time_diff.days == 0:
                return f"🟢 Сегодня в {latest_time} {status_indicator}".strip()
            elif time_diff.days == 1:
                return f"🟡 Вчера в {latest_time} {status_indicator}".strip()
            elif time_diff.days <= 7:
                return f"🟡 {time_diff.days} дней назад ({latest_date.strftime('%d.%m.%Y')}) {status_indicator}".strip()
            else:
                return f"🔴 {time_diff.days} дней назад ({latest_date.strftime('%d.%m.%Y')}) {status_indicator}".strip()
        
        return "⚠️ Информация недоступна"
        
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def _get_backup_schedule():
    """Получает информацию о расписании резервного копирования через Task Scheduler"""
    try:
        # Используем schtasks для получения информации о задачах Windows Backup
        cmd = 'schtasks /query /fo CSV /tn "\\Microsoft\\Windows\\Backup\\*"'
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        
        if proc.returncode == 0:
            raw_bytes = proc.stdout
            detected = chardet.detect(raw_bytes)
            detected_encoding = detected.get("encoding", None)
            confidence = detected.get("confidence", 0)
            
            if detected_encoding and confidence > 0.5:
                decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
            else:
                decoded_output = raw_bytes.decode("cp866", errors="replace")
            
            # Парсим CSV вывод
            lines = [line.strip() for line in decoded_output.splitlines() if line.strip()]
            
            if len(lines) > 1:  # Есть заголовок + данные
                # Ищем задачи, содержащие "Backup" или "WindowsBackup"
                for line in lines[1:]:  # Пропускаем заголовок
                    if "backup" in line.lower() and "ready" in line.lower():
                        # Получаем детальную информацию о найденной задаче
                        task_name = line.split(',')[0].strip('"')
                        schedule_info = _get_task_schedule_details(task_name)
                        if schedule_info:
                            return schedule_info
        
        # Альтернативный метод - PowerShell команда (упрощенная версия вашего скрипта)
        ps_cmd = '''powershell -Command "& {
            try {
                $scheduler = New-Object -ComObject Schedule.Service;
                $scheduler.Connect();
                $folder = $scheduler.GetFolder('\\Microsoft\\Windows\\Backup');
                $tasks = $folder.GetTasks(0);
                foreach ($task in $tasks) {
                    $def = $task.Definition;
                    foreach ($tr in $def.Triggers) {
                        try {
                            $start = [datetime]::Parse($tr.StartBoundary);
                            $time = $start.ToString('HH:mm');
                            if ($tr.Type -eq 2) { Write-Host 'Daily at' $time; }
                            elseif ($tr.Type -eq 3) { Write-Host 'Weekly at' $time; }
                            else { Write-Host 'Scheduled at' $time; }
                            break;
                        } catch {}
                    }
                    break;
                }
            } catch { Write-Host 'Error accessing scheduler'; }
        }"'''
        
        proc2 = subprocess.run(ps_cmd, capture_output=True, shell=True)
        if proc2.returncode == 0:
            raw_bytes2 = proc2.stdout
            detected2 = chardet.detect(raw_bytes2)
            detected_encoding2 = detected2.get("encoding", None)
            confidence2 = detected2.get("confidence", 0)
            
            if detected_encoding2 and confidence2 > 0.5:
                decoded_output2 = raw_bytes2.decode(detected_encoding2, errors="replace")
            else:
                decoded_output2 = raw_bytes2.decode("cp866", errors="replace")
            
            if decoded_output2.strip() and "error" not in decoded_output2.lower():
                return f"🟢 {decoded_output2.strip()}"
        
        # Fallback: анализ частоты создания копий (как раньше)
        recent_dates = _get_recent_backup_dates()
        if len(recent_dates) >= 3:
            intervals = []
            for i in range(1, min(len(recent_dates), 6)):
                diff = (recent_dates[i-1] - recent_dates[i]).total_seconds() / 3600
                intervals.append(diff)
            
            if intervals:
                avg_interval = sum(intervals) / len(intervals)
                times = [date.strftime("%H:%M") for date in recent_dates[:3]]
                common_time = max(set(times), key=times.count) if times else None
                
                if 20 <= avg_interval <= 28:  # Примерно 24 часа
                    if common_time:
                        return f"🟢 Ежедневно в {common_time} (анализ копий)"
                    else:
                        return "🟢 Ежедневно (анализ копий)"
                elif 160 <= avg_interval <= 200:  # Примерно неделя
                    return "🟢 Еженедельно (анализ копий)"
        
        # Если есть недавние копии, значит настроено
        if recent_dates and len(recent_dates) > 0:
            last_backup = recent_dates[0]
            days_ago = (datetime.now() - last_backup).days
            if days_ago <= 2:
                return "🟢 Настроено (есть недавние копии)"
        
        return "❌ Не определено"
        
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def _get_task_schedule_details(task_name):
    """Получает детали расписания для конкретной задачи"""
    try:
        cmd = f'schtasks /query /fo LIST /tn "{task_name}"'
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        
        if proc.returncode == 0:
            raw_bytes = proc.stdout
            detected = chardet.detect(raw_bytes)
            detected_encoding = detected.get("encoding", None)
            confidence = detected.get("confidence", 0)
            
            if detected_encoding and confidence > 0.5:
                decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
            else:
                decoded_output = raw_bytes.decode("cp866", errors="replace")
            
            # Ищем информацию о расписании в выводе
            schedule_type = None
            schedule_time = None
            
            for line in decoded_output.splitlines():
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip()
                    
                    if "schedule type" in key or "тип расписания" in key:
                        if "daily" in value.lower() or "ежедневно" in value.lower():
                            schedule_type = "Ежедневно"
                        elif "weekly" in value.lower() or "еженедельно" in value.lower():
                            schedule_type = "Еженедельно"
                    
                    elif "start time" in key or "время запуска" in key:
                        schedule_time = value
            
            if schedule_type and schedule_time:
                return f"🟢 {schedule_type} в {schedule_time}"
            elif schedule_type:
                return f"🟢 {schedule_type}"
            elif schedule_time:
                return f"🟢 В {schedule_time}"
        
        return None
        
    except Exception as e:
        return None

def _get_recent_backup_dates():
    """Получает список дат последних резервных копий для анализа расписания"""
    try:
        cmd = "wbadmin get versions"
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout
        
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)
        
        if detected_encoding and confidence > 0.5:
            decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_output = raw_bytes.decode("cp866", errors="replace")
        
        dates = []
        lines = [line.strip() for line in decoded_output.splitlines() if line.strip()]
        
        # Ищем даты в формате DD.MM.YYYY HH:MM
        for line in lines:
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})', line)
            if date_match:
                date_str, time_str = date_match.groups()
                try:
                    backup_datetime = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
                    dates.append(backup_datetime)
                except ValueError:
                    continue
        
        # Сортируем по убыванию (новые сначала)
        dates.sort(reverse=True)
        return dates[:10]
        
    except Exception as e:
        return []

def _get_current_backup_status():
    """Получает статус текущей операции резервного копирования"""
    try:
        cmd = "wbadmin get status"
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout
        
        # Применяем тот же подход декодирования что в user_management.py
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)
        
        if detected_encoding and confidence > 0.5:
            decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_output = raw_bytes.decode("cp866", errors="replace")
        
        not_running_phrases = ["не выполняется", "not running", "no operation", "нет операции"]
        running_phrases = ["выполняется", "running", "in progress", "в процессе"]
        
        for phrase in not_running_phrases:
            if phrase in decoded_output.lower():
                return "🟢 Не выполняется"
                
        for phrase in running_phrases:
            if phrase in decoded_output.lower():
                return "🔄 Выполняется"
        
        return "⚠️ Неизвестно"
            
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def _get_storage_info():
    """Получает информацию о месте хранения резервных копий"""
    try:
        lines = []
        
        # Используем ту же логику что и в _get_backup_target_drives()
        target_drives = _get_backup_target_drives()
        
        if target_drives:
            if len(target_drives) == 1:
                lines.append(f"- Место хранения: 🟢 Диск {target_drives[0]}")
            else:
                lines.append(f"- Место хранения: 🟢 Диски {', '.join(target_drives)}")
            return lines
        
        # Если не можем определить диски, не показываем эту строку вообще
        return []
        
    except Exception as e:
        return []  # При ошибке не показываем строку

def _check_backup_health():
    """Проверяет общее состояние системы резервного копирования"""
    try:
        # Проверяем службу Windows Server Backup - используем подход из system_info.py
        service_status = get_service_status("Block Level Backup Engine Service")
        
        if service_status.upper() == "RUNNING":
            return "🟢 Служба активна"
        elif service_status.upper() == "STOPPED":
            return "🔴 Служба остановлена"
        else:
            return f"🟡 Служба: {service_status}"
            
    except Exception as e:
        return f"❌ Ошибка проверки: {str(e)}"

def get_service_status(service_name):
    """
    Проверяет статус службы по её имени (sc query "имя").
    Использует тот же подход что в system_info.py
    """
    try:
        cmd = f'sc query "{service_name}"'
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout

        # Применяем тот же подход декодирования что в system_info.py
        detected = chardet.detect(raw_bytes)
        enc = detected.get("encoding", "cp866")
        decoded = raw_bytes.decode(enc, errors="replace")

        # Пример англ. строки: "STATE              : 4  RUNNING"
        # На русской Windows может быть "СОСТОЯНИЕ         : 4  RUNNING"
        match = re.search(r"(?:STATE|СОСТОЯНИЕ)\s*:\s*\d+\s+(\w+)", decoded, re.IGNORECASE)
        if match:
            state = match.group(1).upper()
            return state  # RUNNING / STOPPED / PAUSED и т.д.
        else:
            return "Не удалось определить статус"
    except Exception as e:
        return f"Ошибка при проверке службы {service_name}: {e}"

def _parse_backup_versions_ru(output):
    """Парсит вывод wbadmin get versions для русской локализации"""
    entries = []
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    
    current_entry = {}
    
    for line in lines:
        line_lower = line.lower()
        
        # Ищем начало новой записи по версии или времени
        if any(phrase in line_lower for phrase in ["версия", "version", "backup time", "время архивации"]):
            if current_entry and current_entry.get("time"):
                entries.append(_format_backup_entry(current_entry))
            current_entry = {}
            
            # Пытаемся извлечь время прямо из этой строки
            time_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})', line)
            if time_match:
                current_entry["time"] = f"{time_match.group(1)} {time_match.group(2)}"
        
        # Ищем дополнительную информацию в строках с двоеточием
        elif ":" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                key = parts[0].strip().lower()
                value = parts[1].strip()
                
                if any(word in key for word in ["время", "time", "дата", "date"]):
                    current_entry["time"] = value
                elif any(word in key for word in ["тип", "type", "режим"]):
                    current_entry["type"] = value
                elif any(word in key for word in ["состояние", "status", "result", "результат", "описание"]):
                    current_entry["status"] = value
    
    # Добавляем последнюю запись
    if current_entry and current_entry.get("time"):
        entries.append(_format_backup_entry(current_entry))
    
    return entries

def _format_backup_entry(entry):
    """Форматирует запись о резервной копии"""
    time_str = entry.get("time", "Время неизвестно")
    type_str = entry.get("type", "")
    status_str = entry.get("status", "")
    
    # Создаем красивое форматирование
    parts = [time_str]
    if type_str:
        parts.append(f"({type_str})")
    if status_str:
        if "успех" in status_str.lower() or "success" in status_str.lower():
            parts.append("✅")
        elif "ошибка" in status_str.lower() or "error" in status_str.lower() or "неудач" in status_str.lower():
            parts.append("❌")
        else:
            parts.append(f"[{status_str}]")
    
    return " ".join(parts)

def _get_backup_target_drives():
    """Получает список целевых дисков для резервного копирования из данных о копиях"""
    try:
        # Получаем точную информацию из summary данных резервных копий
        cmd = "wbadmin get versions -summary"
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        
        if proc.returncode == 0:
            raw_bytes = proc.stdout
            detected = chardet.detect(raw_bytes)
            detected_encoding = detected.get("encoding", None)
            confidence = detected.get("confidence", 0)
            
            if detected_encoding and confidence > 0.5:
                decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
            else:
                decoded_output = raw_bytes.decode("cp866", errors="replace")
            
            # Извлекаем диски из строк "Конечный объект архивации: Несъемный диск с именем G:"
            backup_drives = set()
            for line in decoded_output.splitlines():
                if "конечный объект архивации" in line.lower():
                    match = re.search(r'с именем ([A-Za-z]:)', line)
                    if match:
                        backup_drives.add(match.group(1))
            
            if backup_drives:
                return sorted(list(backup_drives))
        
        # Fallback: если точная информация недоступна, пробуем получить из wbadmin get versions  
        cmd2 = "wbadmin get versions"
        proc2 = subprocess.run(cmd2, capture_output=True, shell=True)
        
        if proc2.returncode == 0:
            raw_bytes2 = proc2.stdout
            detected2 = chardet.detect(raw_bytes2)
            detected_encoding2 = detected2.get("encoding", None)
            confidence2 = detected2.get("confidence", 0)
            
            if detected_encoding2 and confidence2 > 0.5:
                decoded_output2 = raw_bytes2.decode(detected_encoding2, errors="replace")
            else:
                decoded_output2 = raw_bytes2.decode("cp866", errors="replace")
            
            # Ищем диски в обычном выводе wbadmin get versions
            backup_drives2 = set()
            disk_matches = re.findall(r'[A-Za-z]:', decoded_output2)
            for disk in disk_matches:
                if disk not in ['C:', 'D:']:  # Исключаем системные диски
                    backup_drives2.add(disk)
            
            if backup_drives2:
                return sorted(list(backup_drives2))
        
        # Последний fallback: возвращаем все диски с достаточным свободным местом
        drives = []
        cmd3 = 'wmic logicaldisk where "DriveType=3" get DeviceID,FreeSpace,Size'
        proc3 = subprocess.run(cmd3, capture_output=True, shell=True)
        
        if proc3.returncode == 0:
            raw_bytes3 = proc3.stdout
            detected3 = chardet.detect(raw_bytes3)
            detected_encoding3 = detected3.get("encoding", None)
            confidence3 = detected3.get("confidence", 0)
            
            if detected_encoding3 and confidence3 > 0.5:
                decoded_output3 = raw_bytes3.decode(detected_encoding3, errors="replace")
            else:
                decoded_output3 = raw_bytes3.decode("cp866", errors="replace")
            
            lines = [line.strip() for line in decoded_output3.splitlines() if line.strip()]
            
            for line in lines[1:]:  # Пропускаем заголовок
                parts = line.split()
                if len(parts) >= 3:
                    drive = parts[0]
                    try:
                        free_space = int(parts[1])
                        # Если диск имеет более 10 ГБ свободного места, считаем его потенциальной целью
                        if free_space > 10 * 1024 * 1024 * 1024:  # 10 ГБ в байтах
                            drives.append(drive)
                    except:
                        continue
            
            return drives[:3]  # Возвращаем не более 3 дисков
        
        return []
        
    except Exception as e:
        return []

def _get_drive_space(drive):
    """Получает информацию о свободном месте на диске"""
    try:
        cmd = f'wmic logicaldisk where "DeviceID=\'{drive}\'" get FreeSpace,Size'
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout
        
        # Применяем тот же подход декодирования что в user_management.py
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)
        
        if detected_encoding and confidence > 0.5:
            decoded_output = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_output = raw_bytes.decode("cp866", errors="replace")
        
        lines = [line.strip() for line in decoded_output.splitlines() if line.strip()]
        
        if len(lines) > 1:
            parts = lines[1].split()
            if len(parts) >= 2:
                free_space = int(parts[0]) / (1024**3)  # Конвертируем в ГБ
                total_space = int(parts[1]) / (1024**3)
                used_space = total_space - free_space
                used_percent = (used_space / total_space) * 100 if total_space > 0 else 0
                
                emoji = "🔴" if used_percent > 90 else "🟡" if used_percent > 75 else "🟢"
                
                return f"{used_space:.1f}/{total_space:.1f} ГБ ({used_percent:.1f}%) {emoji}"
        
        return "❌ Недоступно"
        
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"