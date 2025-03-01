import subprocess

def reboot_server():
    """
    Выполняет немедленную перезагрузку сервера с помощью shutdown /r /f /t 0.
    """
    try:
        cmd = "shutdown /r /f /t 0"
        result = subprocess.run(cmd, shell=True)
        if result.returncode == 0:
            return True, "Сервер уходит в перезагрузку..."
        else:
            return False, f"Ошибка при попытке перезагрузить сервер. Код возврата: {result.returncode}"
    except Exception as e:
        return False, f"Исключение при перезагрузке сервера: {str(e)}"

def restart_vpn_service():
    """
    Останавливает и запускает службу «Маршрутизация и удаленный доступ» (RemoteAccess).
    """
    try:
        # Останавливаем службу
        cmd_stop = "net stop RemoteAccess"
        result_stop = subprocess.run(cmd_stop, shell=True)
        if result_stop.returncode != 0:
            return False, f"Ошибка при остановке службы (код {result_stop.returncode})."

        # Запускаем службу
        cmd_start = "net start RemoteAccess"
        result_start = subprocess.run(cmd_start, shell=True)
        if result_start.returncode == 0:
            return True, "Служба маршрутизации и удаленного доступа перезапущена."
        else:
            return False, f"Ошибка при запуске службы (код {result_start.returncode})."
    except Exception as e:
        return False, f"Исключение при перезапуске VPN: {str(e)}"
