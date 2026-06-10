# Hushbox - Encrypted Chat

Aplikacja do szyfrowanej komunikacji end-to-end w oparciu o kryptografię krzywych eliptycznych (NaCl/libsodium, algorytm Curve25519 + XSalsa20-Poly1305).

## Struktura projektu

```
chat_app/
├── main.py               # główna aplikacja GUI (CustomTkinter)
├── encryption_manager.py # zarządzanie kluczami i kryptografia
├── chat_store.py         # persystentna historia rozmów
├── my_private_key.bin    # Twój klucz prywatny (NIE udostępniaj!)
├── contact_keys.json     # klucze publiczne kontaktów
├── chat_history/         # historia rozmów (tworzona automatycznie)
└── tests/
    ├── test_encryption_manager.py
    └── test_chat_store.py
```

## Wymagania

```bash
pip install pynacl customtkinter segno Pillow pytest pytest-mock
```

## Uruchomienie

```bash
python main.py
```

## Testy

```bash
pytest tests/ -v
```

## Jak korzystać

### Wymiana kluczy z nowym kontaktem
1. Kliknij **📱 Mój QR** – pojawi się Twój QR kod z kluczem publicznym
2. Poproś kontakt o pokazanie jego QR kodu
3. Zeskanuj lub skopiuj klucz kontaktu do schowka
4. Kliknij **📷 Importuj QR** i podaj nazwę kontaktu

### Wysyłanie wiadomości
1. Wybierz kontakt z listy (otwiera zakładkę rozmowy)
2. Wpisz wiadomość i naciśnij **Enter** lub **Wyślij 🔒**
3. Zaszyfrowany tekst jest automatycznie kopiowany do schowka – wklej go w wybranym komunikatorze

### Odbieranie wiadomości
1. Skopiuj zaszyfrowany tekst od kontaktu
2. W oknie rozmowy kliknij **▼ rozwiń** (panel „Odbierz")
3. Wklej zaszyfrowany tekst i kliknij **Deszyfruj**

### Zarządzanie kontaktami
- Przycisk **⋮** obok kontaktu: edycja, zmiana klucza, usuwanie
- Historia rozmów jest zachowywana lokalnie w `chat_history/`

## Bezpieczeństwo

- Klucz prywatny jest przechowywany **tylko lokalnie** w `my_private_key.bin`
- Szyfrowanie **end-to-end** – zaszyfrowaną wiadomość może odczytać tylko odbiorca
- Każda wiadomość używa **losowego nonce** (nie da się powiązać dwóch wiadomości)
- Aplikacja nie wysyła żadnych danych do sieci
