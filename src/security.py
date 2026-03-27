import base64
import ctypes
from ctypes import wintypes
from pathlib import Path


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32
crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
crypt32.CryptProtectData.restype = wintypes.BOOL
crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
]
crypt32.CryptUnprotectData.restype = wintypes.BOOL
kernel32.LocalFree.argtypes = [ctypes.c_void_p]
kernel32.LocalFree.restype = ctypes.c_void_p


def _to_blob(data: bytes) -> DATA_BLOB:
    buffer = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    ptr = ctypes.cast(blob.pbData, ctypes.POINTER(ctypes.c_ubyte))
    out = bytes(ptr[: blob.cbData])
    kernel32.LocalFree(blob.pbData)
    return out


class SecureTokenStore:
    def __init__(self) -> None:
        self.app_dir = Path.home() / "AppData" / "Roaming" / "MyworkPontoBot"
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.token_file = self.app_dir / "token.dat"

    def save_token(self, token: str) -> None:
        raw = token.encode("utf-8")
        data_in = _to_blob(raw)
        data_out = DATA_BLOB()
        if not crypt32.CryptProtectData(
            ctypes.byref(data_in), "MyworkPontoToken", None, None, None, 0, ctypes.byref(data_out)
        ):
            raise RuntimeError("Falha ao criptografar token com DPAPI.")
        encrypted = _blob_to_bytes(data_out)
        self.token_file.write_text(base64.b64encode(encrypted).decode("ascii"), encoding="utf-8")

    def load_token(self) -> str:
        if not self.token_file.exists():
            return ""
        encrypted = base64.b64decode(self.token_file.read_text(encoding="utf-8"))
        data_in = _to_blob(encrypted)
        data_out = DATA_BLOB()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)
        ):
            return ""
        return _blob_to_bytes(data_out).decode("utf-8")


class SecureCredentialsStore:
    def __init__(self) -> None:
        self.app_dir = Path.home() / "AppData" / "Roaming" / "MyworkPontoBot"
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.credentials_file = self.app_dir / "credentials.dat"

    def save_credentials(self, email: str, password: str) -> None:
        raw = f"{email}\n{password}".encode("utf-8")
        data_in = _to_blob(raw)
        data_out = DATA_BLOB()
        if not crypt32.CryptProtectData(
            ctypes.byref(data_in), "MyworkPontoCredentials", None, None, None, 0, ctypes.byref(data_out)
        ):
            raise RuntimeError("Falha ao criptografar credenciais com DPAPI.")
        encrypted = _blob_to_bytes(data_out)
        self.credentials_file.write_text(base64.b64encode(encrypted).decode("ascii"), encoding="utf-8")

    def load_credentials(self) -> tuple[str, str]:
        if not self.credentials_file.exists():
            return "", ""
        encrypted = base64.b64decode(self.credentials_file.read_text(encoding="utf-8"))
        data_in = _to_blob(encrypted)
        data_out = DATA_BLOB()
        if not crypt32.CryptUnprotectData(
            ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)
        ):
            return "", ""
        raw = _blob_to_bytes(data_out).decode("utf-8")
        email, _, password = raw.partition("\n")
        return email, password
