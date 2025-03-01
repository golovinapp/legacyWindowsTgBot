import subprocess
import re
import time
import chardet
import speedtest

def check_speedtest():
    """
    Выполняет измерение скорости с помощью speedtest.
    Возвращает кортеж (успех: bool, сообщение: str).
    Пример сообщения:
      "Результат Speedtest:
       Ping: 22 мс
       Download: 50.20 Мбит/с
       Upload: 10.30 Мбит/с"
    """
    try:
        s = speedtest.Speedtest()
        s.get_best_server()
        s.download()
        s.upload()
        results = s.results.dict()

        ping = results.get("ping", 0)
        download = results.get("download", 0) / 1_000_000  # перевод в Мбит/с
        upload = results.get("upload", 0) / 1_000_000

        msg = (f"Результат Speedtest:\n"
               f"Ping: {ping:.0f} мс\n"
               f"Download: {download:.2f} Мбит/с\n"
               f"Upload: {upload:.2f} Мбит/с")
        return True, msg
    except Exception as e:
        return False, f"Ошибка при выполнении Speedtest: {e}"

def check_network_status():
    """
    Последовательно выполняет следующие проверки:
      1. Пинг до основного шлюза (локальная сеть)
      2. Пинг до ya.ru и vk.com
      3. nslookup для ya.ru (проверка DNS)
      4. Оценка загрузки сетевого интерфейса
    Возвращает кортеж (успех: bool, сообщение: str) с подробным результатом и итоговым заключением:
      - "Связь в порядке" – если все проверки пройдены и задержки нормальные,
      - "Проблема с локальной сетью" – если шлюз недоступен,
      - "Проблема с интернетом" – если внешние узлы или DNS недоступны,
      - "Задержки в соединении" – если пинг превышает порог (например, >100 мс).
    """
    max_ping_ms = 100  # порог задержки
    gateway_ip = "77.247.243.1"  # замените на реальный IP вашего шлюза

    checks = []
    gw_ok, gw_ping = _ping_host(gateway_ip, count=5)
    checks.append(("Локальная сеть (шлюз)", gw_ok, gw_ping))
    
    ya_ok, ya_ping = _ping_host("ya.ru", count=5)
    checks.append(("ya.ru", ya_ok, ya_ping))
    
    vk_ok, vk_ping = _ping_host("vk.com", count=5)
    checks.append(("vk.com", vk_ok, vk_ping))
    
    dns_ok, dns_result = _nslookup("ya.ru")
    checks.append(("DNS (ya.ru)", dns_ok, dns_result))
    
    net_ok, net_usage_msg = _check_interface_usage()
    checks.append(("Сетевой интерфейс", net_ok, net_usage_msg))
    
    all_ok = all(x[1] for x in checks)
    have_delays = False

    # Анализируем результаты пинга на наличие задержек
    for name, ok, detail in checks:
        # Ищем слово "Average" или "Среднее" и число мс
        match = re.search(r"(?:Average|Среднее)\s*=\s*(\d+)", detail)
        if match:
            avg_ping = int(match.group(1))
            if avg_ping > max_ping_ms:
                have_delays = True

    # Формируем итоговое заключение
    if not gw_ok:
        summary = "Проблема с локальной сетью"
    elif not ya_ok or not vk_ok or not dns_ok:
        summary = "Проблема с интернетом"
    elif have_delays:
        summary = "Задержки в соединении"
    else:
        summary = "Связь в порядке"

    lines = []
    for name, ok, detail in checks:
        status = "OK" if ok else "Ошибка"
        lines.append(f"{name}: {status} ({detail})")
    lines.append(f"\nИтог: {summary}")
    return all_ok, "\n".join(lines)

def check_custom_connection(target):
    """
    Выполняет проверку связи до произвольного узла (IP или домена).
    Проводит пинг (10 пакетов) и трассировку (tracert).
    Возвращает кортеж (успех: bool, сообщение: str) с кратким отчетом.
    """
    try:
        ok, ping_msg = _ping_host(target, count=10)
        tracert_msg = _traceroute(target)
        result = (f"Проверка связи до узла: {target}\n\n"
                  f"=== Результаты ping ===\n{ping_msg}\n\n"
                  f"=== Трассировка ===\n{tracert_msg}\n")
        return ok, result
    except Exception as e:
        return False, f"Ошибка при проверке связи до {target}: {e}"

# Вспомогательные функции

def _ping_host(host, count=4):
    """
    Выполняет ping -n <count> <host>, получает сырые байты вывода,
    определяет кодировку с помощью chardet и декодирует результат.
    
    Ищет в одной строке или нескольких подряд:
      - (Sent|Отправлено) = <число>
      - (Received|получено) = <число>
      - (Lost|Потеряно) = <число>
      - (Average|Среднее) = <число> (в отдельном регулярном выражении)

    Возвращает (ok: bool, details: str).
    Если статистика не найдена, возвращается сообщение об ошибке.
    """
    try:
        cmd = f'ping -n {count} {host}'
        print(f"DEBUG: Выполняется команда: {cmd}")
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout

        print("DEBUG: Сырые байты вывода ping:", raw_bytes)

        detected = chardet.detect(raw_bytes)
        encoding = detected.get("encoding", "cp866")
        confidence = detected.get("confidence", 0)
        print(f"DEBUG: Определена кодировка: {encoding} (уверенность: {confidence})")

        decoded_output = raw_bytes.decode(encoding, errors="replace")
        # Показываем «сырой» декодированный текст и его repr,
        # чтобы точно увидеть невидимые символы, пробелы и т.д.
        print("DEBUG: repr(decoded_output) =>", repr(decoded_output))
        print("DEBUG: Декодированный вывод команды ping:\n", decoded_output)

        # Ищем суммарную статистику пакетов. Используем DOTALL (re.DOTALL),
        # чтобы .* мог захватить перевод строки. IGNORECASE для учёта регистра.
        stats_match = re.search(
            r"(?:Sent|Отправлено)\s*=\s*(\d+).*?"
            r"(?:Received|получено)\s*=\s*(\d+).*?"
            r"(?:Lost|Потеряно)\s*=\s*(\d+)",
            decoded_output,
            flags=re.IGNORECASE | re.DOTALL
        )

        if not stats_match:
            return False, "Ping: статистика не найдена"

        sent_val = int(stats_match.group(1))
        rec_val = int(stats_match.group(2))
        lost_val = int(stats_match.group(3))

        # Ищем средний пинг (Average/Среднее)
        avg_match = re.search(
            r"(?:Average|Среднее)\s*=\s*(\d+)",
            decoded_output,
            flags=re.IGNORECASE
        )
        avg_val = int(avg_match.group(1)) if avg_match else -1

        ok = (rec_val > 0 and lost_val == 0)
        details = (f"Packets: Sent={sent_val}, Received={rec_val}, Lost={lost_val}, "
                   f"Avg={avg_val if avg_val >= 0 else '??'} ms")
        return ok, details

    except Exception as e:
        return False, f"Ошибка пинга: {e}"

def _traceroute(host):
    """
    Выполняет tracert <host>, получает сырые байты вывода,
    определяет кодировку с помощью chardet и возвращает декодированный результат.
    """
    try:
        cmd = f'tracert {host}'
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout
        
        detected = chardet.detect(raw_bytes)
        encoding = detected.get("encoding", "cp866")
        decoded_output = raw_bytes.decode(encoding, errors="replace")
        return decoded_output
    except Exception as e:
        return f"Ошибка трассировки: {e}"

def _nslookup(host):
    """
    Выполняет nslookup <host> и возвращает (ok: bool, details: str).
    Если в выводе присутствуют ключевые слова ("Name:" или "Addresses:"), считается, что проверка прошла успешно.
    """
    try:
        cmd = f'nslookup {host}'
        proc = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = proc.stdout
        
        detected = chardet.detect(raw_bytes)
        encoding = detected.get("encoding", "cp866")
        decoded_output = raw_bytes.decode(encoding, errors="replace")
        
        if "Name:" in decoded_output or "Addresses:" in decoded_output:
            return True, "nslookup OK"
        else:
            return False, decoded_output.strip()
    except Exception as e:
        return False, f"Ошибка nslookup: {e}"

def _check_interface_usage():
    """
    Проводит упрощённую проверку загрузки сетевого интерфейса.
    Делает два замера BytesTotalPerSec с паузой в 1 секунду и вычисляет разницу.
    Возвращает (ok: bool, details: str).
    """
    try:
        val1 = _get_bytes_total_per_sec()
        time.sleep(1)
        val2 = _get_bytes_total_per_sec()
        if val1 < 0 or val2 < 0:
            return False, "Не удалось получить данные о трафике"
        bytes_per_sec = (val2 - val1)
        mbits_per_sec = (bytes_per_sec * 8) / (1024 * 1024)
        # Предположим, пропускная способность равна 1 Gbit/s
        usage_percent = (mbits_per_sec / 1000) * 100
        return True, f"~{mbits_per_sec:.2f} Mбит/с ({usage_percent:.1f}% от 1G)"
    except Exception as e:
        return False, f"Ошибка при измерении интерфейса: {e}"

def _get_bytes_total_per_sec():
    """
    Получает суммарное значение BytesTotalPerSec для всех сетевых интерфейсов.
    Возвращает целое число или -1 при ошибке.
    """
    try:
        cmd = 'wmic path Win32_PerfFormattedData_Tcpip_NetworkInterface get BytesTotalPerSec'
        proc = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if len(lines) <= 1:
            return -1
        total = 0
        for line in lines[1:]:
            try:
                total += int(line)
            except:
                pass
        return total if total else -1
    except Exception as e:
        return -1
