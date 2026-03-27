import os
import sys
import winreg


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "MyworkPontoBot"


def set_startup(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_ALL_ACCESS) as key:
        if enabled:
            executable = sys.executable
            if executable.lower().endswith("python.exe"):
                launch_cmd = f'"{executable}" "{os.path.abspath("main.py")}" --minimized'
            else:
                launch_cmd = f'"{executable}" --minimized'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def is_startup_enabled() -> bool:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
        try:
            winreg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False
