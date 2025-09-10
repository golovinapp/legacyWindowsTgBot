import subprocess
import chardet
import re
from backup_monitoring import _get_backup_schedule

def get_server_load():
    """
    Расширенная функция, которая:
      1) Получает загрузку CPU, память и информацию по дискам.
      2) Проверяет статус служб "1C:Enterprise 8.2 Server Agent" и "1C:Enterprise 8.3 Server Agent".
      3) Получает расписание резервного копирования.
      4) Получает время загрузки системы.
      5) Формирует общий текстовый отчёт о состоянии сервера.
    """
    try:
        # 1. Получаем загрузку CPU
        cpu_load, cpu_emoji = _get_cpu_usage()

        # 2. Получаем данные по памяти
        mem_usage_str, mem_emoji = _get_memory_usage()

        # 3. Получаем информацию о дисках
        disk_lines = _get_disks_info()

        # 4. Проверяем статус служб 1С
        service_82_status = get_service_status("1C:Enterprise 8.2 Server Agent")
        service_83_status = get_service_status("1C:Enterprise 8.3 Server Agent")

        # Определяем эмоджи в зависимости от статуса (RUNNING => 🟢, иначе => 🔴)
        service_82_emoji = "🟢" if service_82_status.upper() == "RUNNING" else "🔴"
        service_83_emoji = "🟢" if service_83_status.upper() == "RUNNING" else "🔴"

        # 5. Получаем время загрузки системы
        boot_time_str = _get_boot_time()
        
        # 6. Получаем расписание резервного копирования
        backup_schedule = _get_backup_schedule()

        # Формируем финальный вывод
        lines = []
        lines.append("Состояние сервера:")
        lines.append(f"- CPU: {cpu_load}% {cpu_emoji}")
        lines.append(f"- Память: {mem_usage_str} {mem_emoji}")

        # Добавляем строки о дисках
        lines.extend(disk_lines)

        # Добавляем строки о статусах служб 1С
        lines.append(f"- Служба 1С 8.2: {service_82_status} {service_82_emoji}")
        lines.append(f"- Служба 1С 8.3: {service_83_status} {service_83_emoji}")
        
        # Добавляем расписание резервного копирования
        lines.append(f"- Резервное копирование: {backup_schedule}")

        # Время загрузки — последняя строка
        lines.append(f"- Время загрузки системы: {boot_time_str}")

        return "\n".join(lines)
    except Exception as e:
        return f"Ошибка получения данных о сервере: {str(e)}"

# ------------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ------------------------------------------------------------------------------

def _get_cpu_usage():
    """
    Возвращает (процент_загрузки, emoji).
    Если >80%, то красный кружок, иначе зелёный.
    """
    cmd = "wmic cpu get loadpercentage"
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=True, encoding='cp866')
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    cpu_load = "0"
    if len(lines) > 1:
        cpu_load = lines[1]  # вторая строка обычно число
    cpu_load = cpu_load.strip() or "0"

    try:
        cpu_value = float(cpu_load)
    except ValueError:
        cpu_value = 0.0

    cpu_emoji = "🔴" if cpu_value > 80 else "🟢"
    return cpu_load, cpu_emoji

def _get_memory_usage():
    """
    Возвращает (строка_использования_памяти, emoji).
    Если >80%, то красный кружок, иначе зелёный.
    """
    cmd = "wmic OS get FreePhysicalMemory,TotalVisibleMemorySize"
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=True, encoding='cp866')
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    mem_usage_str = "Неизвестно"
    mem_emoji = "🟢"
    if len(lines) > 1:
        mem_data = lines[1].split()
        if len(mem_data) >= 2:
            free_mem_kb = int(mem_data[0])
            total_mem_kb = int(mem_data[1])
            free_mem_mb = free_mem_kb / 1024
            total_mem_mb = total_mem_kb / 1024
            used_mem_mb = total_mem_mb - free_mem_mb
            mem_percent = (used_mem_mb / total_mem_mb) * 100
            mem_usage_str = f"{used_mem_mb:.1f}/{total_mem_mb:.1f} MB ({mem_percent:.1f}%)"
            if mem_percent > 80:
                mem_emoji = "🔴"
    return mem_usage_str, mem_emoji

def _get_disks_info():
    """
    Возвращает список строк с информацией по всем дискам DriveType=3.
    Пример: ["- Диск (C:): 12.3/100.0 GB (12.3%) 🟢", "- Диск (D:): ..."]
    """
    lines_result = []
    cmd = 'wmic logicaldisk where "DriveType=3" get DeviceID,FreeSpace,Size'
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=True, encoding='cp866')
    raw_lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    # Первая строка - заголовок
    for line in raw_lines[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        device_id = parts[0]
        free_str = parts[1]
        size_str = parts[2]
        try:
            free_space = int(free_str)
            size = int(size_str)
            free_gb = free_space / (1024**3)
            total_gb = size / (1024**3)
            used_gb = total_gb - free_gb
            used_percent = (used_gb / total_gb) * 100 if total_gb > 0 else 0
            disk_emoji = "🔴" if used_percent >= 95 else "🟢"

            line_str = (f"- Диск ({device_id}): "
                        f"{used_gb:.1f}/{total_gb:.1f} GB ({used_percent:.1f}%) {disk_emoji}")
            lines_result.append(line_str)
        except:
            continue
    return lines_result

def get_service_status(service_name):
    """
    Проверяет статус службы по её имени (sc query "имя").
    Возвращает:
      - "RUNNING", "STOPPED" (или иной статус, если удастся вытащить),
      - "Не удалось определить статус (регексы не сработали)" – если шаблон не совпал,
      - "Ошибка ..." – если что-то пошло не так.

    В консоль выводятся отладочные данные о выполнении команды и декодировании.
    """
    try:
        cmd = f'sc query "{service_name}"'
        print("DEBUG: Выполняется команда:", cmd)
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout

        print("DEBUG: Сырые байты вывода sc query:", raw_bytes)

        detected = chardet.detect(raw_bytes)
        enc = detected.get("encoding", "cp866")
        conf = detected.get("confidence", 0)
        print(f"DEBUG: Определена кодировка: {enc} (уверенность: {conf})")

        decoded = raw_bytes.decode(enc, errors="replace")
        print("DEBUG: Декодированный вывод sc query:\n", decoded)

        # Пример англ. строки: "STATE              : 4  RUNNING"
        # На русской Windows может быть "СОСТОЯНИЕ         : 4  RUNNING"
        # Добавляем оба варианта через (?:STATE|СОСТОЯНИЕ).
        # Если служба не найдена, может быть другая строка (см. отладочный вывод).
        match = re.search(r"(?:STATE|СОСТОЯНИЕ)\s*:\s*\d+\s+(\w+)", decoded, re.IGNORECASE)
        if match:
            state = match.group(1).upper()
            return state  # RUNNING / STOPPED / PAUSED и т.д.
        else:
            return "Не удалось определить статус (регексы не сработали)"
    except Exception as e:
        return f"Ошибка при проверке службы {service_name}: {e}"

def _get_boot_time():
    """
    Вызывает systeminfo, декодирует вывод с помощью chardet,
    ищет строку, начинающуюся с "Время загрузки системы:" (на русской Windows).
    Возвращает строку вида "01.03.2025, 12:15:30" или "Неизвестно".
    """
    try:
        cmd = "systeminfo"
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout

        detected = chardet.detect(raw_bytes)
        enc = detected.get("encoding", "cp866")
        decoded = raw_bytes.decode(enc, errors="replace")

        lines = [l.strip() for l in decoded.splitlines() if l.strip()]
        for line in lines:
            # Ищем строку, начинающуюся с "Время загрузки системы:"
            if line.lower().startswith("время загрузки системы:"):
                # Обрезаем сам заголовок
                return line.split(":", 1)[1].strip()
        return "Неизвестно"
    except Exception as e:
        return f"Ошибка чтения systeminfo: {e}"