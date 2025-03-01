import subprocess
import re
import chardet

def get_vpn_sessions():
    """
    Получаем список VPN-сессий, определяя кодировку вывода автоматически.
    Сохраняем результат в vpn_sessions.txt.
    """
    try:
        # 1. Вызываем netsh без text=True и без encoding=..., чтобы получить сырые байты
        result = subprocess.run(
            "netsh ras show client",
            capture_output=True,
            shell=True
        )
        raw_bytes = result.stdout

        # 2. Определяем кодировку с помощью chardet
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)

        print(f"Определена кодировка: {detected_encoding}, уверенность: {confidence}")

        # 3. Если chardet уверенно определил кодировку, используем её;
        #    иначе пробуем cp866 как самую распространённую для старых русских Windows.
        if detected_encoding and confidence > 0.5:
            decoded_text = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_text = raw_bytes.decode("cp866", errors="replace")

        # 4. Разбиваем результат на строки
        lines = [line.strip() for line in decoded_text.splitlines() if line.strip()]

        print("Вывод netsh ras show client (raw -> декодированный):")
        for line in lines:
            print(f"Строка: {line}")

        vpn_sessions = []
        current_user = None
        current_duration = None

        # Пример: ищем "Пользователь:" и "Длительность:"
        # Если у вас в выводе другие ключевые слова (например, "Время:"), подставьте их.
        for line in lines:
            if line.startswith("Пользователь:"):
                if current_user is not None:
                    vpn_sessions.append({
                        "name": current_user,
                        "connect_time": current_duration or "Неизвестно"
                    })
                current_user = line.replace("Пользователь:", "").strip()
                current_duration = None
            elif line.startswith("Длительность:"):
                current_duration = line.replace("Длительность:", "").strip()

        # Добавляем последнего пользователя, если он есть
        if current_user is not None:
            vpn_sessions.append({
                "name": current_user,
                "connect_time": current_duration or "Неизвестно"
            })

        # Сохраняем в файл
        with open("vpn_sessions.txt", "w", encoding="utf-8") as f:
            f.write("Имя пользователя;Длительность\n")
            for sess in vpn_sessions:
                f.write(f"{sess['name']};{sess['connect_time']}\n")

        return vpn_sessions

    except Exception as e:
        print(f"Ошибка при получении VPN-соединений: {e}")
        return []

def reset_vpn_session(user_name):
    """
    Читает vpn_sessions.txt, ищет user_name, выполняет команду netsh ras set client <user> disconnect
    с автоматическим определением кодировки для проверки результата.
    """
    try:
        print("### НАЧАЛО СБРОСА VPN-СЕССИИ ###")
        print(f"Попытка отключения пользователя: {user_name}")

        # Читаем файл vpn_sessions.txt
        try:
            with open("vpn_sessions.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            return False, "Файл vpn_sessions.txt не найден. Сначала запросите список VPN-сессий."

        lines = [l.strip() for l in lines if l.strip()]
        if len(lines) <= 1:
            return False, "В файле vpn_sessions.txt нет данных о пользователях."

        data_lines = lines[1:]
        matched_user = None
        for line in data_lines:
            parts = line.split(";")
            if len(parts) < 2:
                continue
            if parts[0] == user_name:
                matched_user = parts[0]
                break

        if not matched_user:
            return False, f"Пользователь {user_name} не найден в vpn_sessions.txt"

        # Формируем команду
        if " " in matched_user:
            cmd = f'netsh ras set client "{matched_user}" disconnect'
        else:
            cmd = f"netsh ras set client {matched_user} disconnect"

        print(f"Команда для выполнения: {cmd}")
        result = subprocess.run(cmd, capture_output=True, shell=True)
        raw_bytes = result.stdout

        # Аналогично определяем кодировку для результата
        detected = chardet.detect(raw_bytes)
        detected_encoding = detected.get("encoding", None)
        confidence = detected.get("confidence", 0)

        if detected_encoding and confidence > 0.5:
            decoded_stdout = raw_bytes.decode(detected_encoding, errors="replace")
        else:
            decoded_stdout = raw_bytes.decode("cp866", errors="replace")

        print("Вывод netsh ras set client disconnect (декодированный):")
        print(decoded_stdout)
        print(f"STDERR: {result.stderr}")
        print(f"Код возврата: {result.returncode}")

        # Теперь проверяем, отключён ли пользователь
        verification = subprocess.run(
            "netsh ras show client", capture_output=True, shell=True
        )
        ver_raw = verification.stdout
        ver_detected = chardet.detect(ver_raw)
        ver_enc = ver_detected.get("encoding", None)
        ver_conf = ver_detected.get("confidence", 0)

        if ver_enc and ver_conf > 0.5:
            ver_decoded = ver_raw.decode(ver_enc, errors="replace")
        else:
            ver_decoded = ver_raw.decode("cp866", errors="replace")

        print("Проверка после сброса (netsh ras show client):")
        print(ver_decoded)

        if result.returncode == 0:
            # Проверяем, исчезла ли строка "Пользователь: matched_user"
            if f"Пользователь: {matched_user}" not in ver_decoded:
                return True, f"VPN-соединение {matched_user} сброшено."
            else:
                return False, f"Пользователь {matched_user} всё ещё отображается."
        else:
            return False, (
                f"Ошибка: не удалось сбросить VPN-соединение {matched_user}. "
                f"Код ошибки: {result.returncode}, Вывод: {decoded_stdout or result.stderr}"
            )
    except Exception as e:
        return False, f"Исключение при сбросе VPN-сессии {user_name}: {str(e)}"
    finally:
        print("### КОНЕЦ СБРОСА VPN-СЕССИИ ###")
