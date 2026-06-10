"""
EncryptionManager - obsługuje klucze NaCl i szyfrowanie/deszyfrowanie wiadomości.
"""
from nacl.public import PrivateKey, PublicKey, Box
from nacl.encoding import Base64Encoder
import json
import os
from pathlib import Path


class EncryptionManager:
    def __init__(self, data_dir: str = "."):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.private_key_path = self.data_dir / "my_private_key.bin"
        self.contact_keys_path = self.data_dir / "contact_keys.json"

        self.private_key = self._load_or_generate_private_key()
        self.public_key = self.private_key.public_key
        self.contact_keys: dict[str, str] = self._load_contact_keys()

    # ------------------------------------------------------------------
    # Klucze własne
    # ------------------------------------------------------------------

    def _load_or_generate_private_key(self) -> PrivateKey:
        """Załaduj klucz prywatny z pliku lub wygeneruj nowy."""
        if self.private_key_path.exists():
            with open(self.private_key_path, "rb") as f:
                return PrivateKey(f.read())
        key = PrivateKey.generate()
        with open(self.private_key_path, "wb") as f:
            f.write(bytes(key))
        return key

    def export_public_key(self) -> str:
        """Zwróć własny klucz publiczny jako base64 string."""
        return self.public_key.encode(encoder=Base64Encoder).decode()

    # ------------------------------------------------------------------
    # Kontakty
    # ------------------------------------------------------------------

    def _load_contact_keys(self) -> dict[str, str]:
        """Załaduj klucze kontaktów z pliku JSON."""
        if self.contact_keys_path.exists():
            with open(self.contact_keys_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_contact_keys(self) -> None:
        """Zapisz kontakty do pliku JSON."""
        with open(self.contact_keys_path, "w", encoding="utf-8") as f:
            json.dump(self.contact_keys, f, indent=2, ensure_ascii=False)

    def add_contact(self, name: str, public_key_b64: str) -> None:
        """Dodaj lub zaktualizuj kontakt."""
        name = name.strip()
        if not name:
            raise ValueError("Nazwa kontaktu nie może być pusta.")
        # walidacja klucza
        PublicKey(public_key_b64.encode(), encoder=Base64Encoder)
        self.contact_keys[name] = public_key_b64
        self._save_contact_keys()

    def remove_contact(self, name: str) -> None:
        """Usuń kontakt."""
        if name not in self.contact_keys:
            raise KeyError(f"Kontakt '{name}' nie istnieje.")
        del self.contact_keys[name]
        self._save_contact_keys()

    def rename_contact(self, old_name: str, new_name: str) -> None:
        """Zmień nazwę kontaktu."""
        new_name = new_name.strip()
        if old_name not in self.contact_keys:
            raise KeyError(f"Kontakt '{old_name}' nie istnieje.")
        if not new_name:
            raise ValueError("Nowa nazwa nie może być pusta.")
        self.contact_keys[new_name] = self.contact_keys.pop(old_name)
        self._save_contact_keys()

    def list_contacts(self) -> list[str]:
        """Zwróć posortowaną listę nazw kontaktów."""
        return sorted(self.contact_keys.keys())

    def has_contact(self, name: str) -> bool:
        return name in self.contact_keys

    # ------------------------------------------------------------------
    # Szyfrowanie / Deszyfrowanie
    # ------------------------------------------------------------------

    def _get_box(self, contact_name: str) -> Box:
        if contact_name not in self.contact_keys:
            raise KeyError(f"Brak klucza publicznego dla kontaktu '{contact_name}'.")
        recipient_key = PublicKey(
            self.contact_keys[contact_name].encode(),
            encoder=Base64Encoder,
        )
        return Box(self.private_key, recipient_key)

    def encrypt(self, contact_name: str, plaintext: str) -> str:
        """Zaszyfruj wiadomość dla kontaktu, zwróć base64 string."""
        box = self._get_box(contact_name)
        encrypted = box.encrypt(plaintext.encode("utf-8"), encoder=Base64Encoder)
        return encrypted.decode()

    def decrypt(self, contact_name: str, ciphertext: str) -> str:
        """Odszyfruj wiadomość od kontaktu, zwróć plaintext."""
        box = self._get_box(contact_name)
        decrypted = box.decrypt(ciphertext.strip().encode(), encoder=Base64Encoder)
        return decrypted.decode("utf-8")
