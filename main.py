"""
Hushbox Encrypted Chat - główna aplikacja GUI.

Układ:
  ┌─────────────────────────────────────────────────────────────┐
  │  SIDEBAR (kontakty)  │  NOTEBOOK (zakładki rozmów)          │
  │                      │  ┌──────────────────────────────────┐│
  │  [+ Dodaj kontakt]   │  │  historia czatu (scrollable)     ││
  │  [kontakt 1]         │  │                                  ││
  │  [kontakt 2]         │  │                                  ││
  │  ...                 │  ├──────────────────────────────────┤│
  │                      │  │  [pole do wpisywania]  [Wyślij]  ││
  │  ──────────────────  │  └──────────────────────────────────┘│
  │  [Mój QR]            │                                       │
  │  [Importuj QR]       │                                       │
  └─────────────────────────────────────────────────────────────┘

Każde kliknięcie kontaktu otwiera/przełącza zakładkę z historią rozmowy.
Pole "Wklej zaszyfrowaną" jest widoczne po rozwinięciu panelu "Odbierz".
"""

import json
import tkinter as tk
from tkinter import messagebox, simpledialog
import customtkinter as ctk
from PIL import Image, ImageTk

from encryption_manager import EncryptionManager
from chat_store import ChatStore, Message


# ─────────────────────────────────────────────────────────────────
# Stałe wizualne
# ─────────────────────────────────────────────────────────────────
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_LABEL = ("Segoe UI", 12)
FONT_MONO  = ("Consolas", 11)
FONT_SMALL = ("Segoe UI", 10)

COLOR_SENT  = "#1a6b3c"   # ciemna zieleń - wiadomości wychodzące
COLOR_RECV  = "#1a3a6b"   # ciemny niebieski - wiadomości przychodzące
COLOR_CIPHER = "#555555"  # szary - tekst zaszyfrowany

DATA_DIR = "."


# ─────────────────────────────────────────────────────────────────
# Okno dodawania / edycji kontaktu
# ─────────────────────────────────────────────────────────────────
class ContactDialog(ctk.CTkToplevel):
    """Modal do dodawania / edytowania kontaktu."""

    def __init__(self, parent, title: str, name: str = "", key: str = ""):
        super().__init__(parent)
        self.title(title)
        self.geometry("520x320")
        self.resizable(False, False)
        self.grab_set()
        self.result: tuple[str, str] | None = None

        ctk.CTkLabel(self, text="Nazwa kontaktu:", font=FONT_LABEL).pack(anchor="w", padx=20, pady=(20, 2))
        self.name_entry = ctk.CTkEntry(self, width=480, placeholder_text="np. Jan Kowalski")
        self.name_entry.pack(padx=20)
        if name:
            self.name_entry.insert(0, name)

        ctk.CTkLabel(self, text="Klucz publiczny (base64):", font=FONT_LABEL).pack(anchor="w", padx=20, pady=(14, 2))
        self.key_entry = ctk.CTkEntry(self, width=480, placeholder_text="Wklej klucz base64 lub skan z QR...")
        self.key_entry.pack(padx=20)
        if key:
            self.key_entry.insert(0, key)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="Zapisz", width=120, command=self._save).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Anuluj", width=120, fg_color="#555", command=self.destroy).pack(side="left", padx=10)

        self.name_entry.focus()

    def _save(self):
        name = self.name_entry.get().strip()
        key  = self.key_entry.get().strip()
        if not name:
            messagebox.showerror("Błąd", "Nazwa kontaktu jest wymagana.", parent=self)
            return
        if not key:
            messagebox.showerror("Błąd", "Klucz publiczny jest wymagany.", parent=self)
            return
        self.result = (name, key)
        self.destroy()


# ─────────────────────────────────────────────────────────────────
# Panel QR
# ─────────────────────────────────────────────────────────────────
class QRWindow(ctk.CTkToplevel):
    def __init__(self, parent, public_key_b64: str):
        super().__init__(parent)
        self.title("Mój klucz publiczny – QR")
        self.geometry("520x560")
        self.resizable(False, False)

        try:
            import segno
            data = json.dumps({"public_key": public_key_b64})
            qr = segno.make(data, error="M")
            qr_path = "my_public_key_qr.png"
            qr.save(qr_path, scale=6, border=2)

            ctk.CTkLabel(self, text="Pokaż ten QR kontaktowi, by dodał Cię do listy.", font=FONT_SMALL).pack(pady=(16, 4))

            img = Image.open(qr_path).resize((320, 320))
            photo = ImageTk.PhotoImage(img)
            lbl = ctk.CTkLabel(self, image=photo, text="")
            lbl.image = photo
            lbl.pack()

            key_box = ctk.CTkTextbox(self, height=80, width=480, font=FONT_MONO)
            key_box.insert("1.0", public_key_b64)
            key_box.configure(state="disabled")
            key_box.pack(pady=10, padx=20)

            ctk.CTkButton(self, text="Kopiuj klucz", command=lambda: self._copy(public_key_b64)).pack(pady=4)

        except Exception as e:
            ctk.CTkLabel(self, text=f"Błąd generowania QR:\n{e}", wraplength=480).pack(pady=30)

        ctk.CTkButton(self, text="Zamknij", fg_color="#555", command=self.destroy).pack(pady=10)

    def _copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Skopiowano", "Klucz publiczny skopiowany do schowka.", parent=self)


# ─────────────────────────────────────────────────────────────────
# Panel "Odbierz wiadomość" (wklej zaszyfrowany tekst)
# ─────────────────────────────────────────────────────────────────
class ReceivePanel(ctk.CTkFrame):
    def __init__(self, parent, on_decrypt_cb):
        super().__init__(parent, fg_color="transparent")
        self._on_decrypt = on_decrypt_cb

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text="📥 Odbierz zaszyfrowaną wiadomość", font=FONT_LABEL).pack(side="left", padx=6)
        self._toggle_btn = ctk.CTkButton(header, text="▼ rozwiń", width=90,
                                          fg_color="#444", command=self._toggle)
        self._toggle_btn.pack(side="right", padx=6)

        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body_visible = False

        inner = ctk.CTkFrame(self._body, fg_color="transparent")
        inner.pack(fill="x", padx=6, pady=4)

        self.cipher_entry = ctk.CTkEntry(inner, placeholder_text="Wklej zaszyfrowany tekst base64...", font=FONT_MONO)
        self.cipher_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.cipher_entry.bind("<Return>", lambda _: self._on_decrypt(self.cipher_entry.get()))

        ctk.CTkButton(inner, text="Deszyfruj", width=90,
                      command=lambda: self._on_decrypt(self.cipher_entry.get())).pack(side="right")

    def _toggle(self):
        if self._body_visible:
            self._body.pack_forget()
            self._toggle_btn.configure(text="▼ rozwiń")
        else:
            self._body.pack(fill="x")
            self._toggle_btn.configure(text="▲ zwiń")
            self.cipher_entry.focus()
        self._body_visible = not self._body_visible

    def clear(self):
        self.cipher_entry.delete(0, "end")


# ─────────────────────────────────────────────────────────────────
# Zakładka rozmowy z jednym kontaktem
# ─────────────────────────────────────────────────────────────────
class ChatTab(ctk.CTkFrame):
    def __init__(self, parent, contact_name: str,
                 enc_manager: EncryptionManager, chat_store: ChatStore):
        super().__init__(parent, fg_color="transparent")
        self.contact_name = contact_name
        self._enc = enc_manager
        self._store = chat_store
        self._build_ui()
        self._load_history()

    def _build_ui(self):
        # ── Historia czatu ──
        self.history = ctk.CTkTextbox(self, font=FONT_LABEL, state="disabled", wrap="word")
        self.history.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        # tagi kolorystyczne
        self.history._textbox.tag_configure("sent_label",   foreground=COLOR_SENT,   font=(FONT_LABEL[0], FONT_LABEL[1], "bold"))
        self.history._textbox.tag_configure("sent_text",    foreground=COLOR_SENT)
        self.history._textbox.tag_configure("recv_label",   foreground="#4fa3e3",     font=(FONT_LABEL[0], FONT_LABEL[1], "bold"))
        self.history._textbox.tag_configure("recv_text",    foreground="#4fa3e3")
        self.history._textbox.tag_configure("cipher_text",  foreground=COLOR_CIPHER,  font=(FONT_MONO[0], 9))
        self.history._textbox.tag_configure("timestamp",    foreground="#888888",     font=(FONT_SMALL[0], 9))
        self.history._textbox.tag_configure("separator",    foreground="#444444")

        # ── Panel odbierania ──
        self._receive_panel = ReceivePanel(self, on_decrypt_cb=self._handle_decrypt)
        self._receive_panel.pack(fill="x", padx=8, pady=(4, 0))

        # ── Pole wpisywania + przycisk Wyślij ──
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.pack(fill="x", padx=8, pady=(4, 8))

        self.msg_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text=f"Wiadomość do {self.contact_name}...",
            font=FONT_LABEL,
        )
        self.msg_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.msg_entry.bind("<Return>", lambda _: self._send())
        self.msg_entry.bind("<Shift-Return>", lambda _: None)   # ignorujemy shift-enter

        self._send_btn = ctk.CTkButton(input_frame, text="Wyślij 🔒", width=110, command=self._send)
        self._send_btn.pack(side="right")

    # ── Ładowanie historii ──────────────────────────────────────

    def _load_history(self):
        msgs = self._store.load(self.contact_name)
        for msg in msgs:
            self._render_message(msg, scroll=False)
        self.history.see("end")

    # ── Renderowanie wiadomości ─────────────────────────────────

    def _render_message(self, msg: Message, scroll: bool = True):
        tb = self.history._textbox
        self.history.configure(state="normal")

        if msg.direction == "out":
            tb.insert("end", f"[{msg.timestamp}] ", "timestamp")
            tb.insert("end", "Ty: ", "sent_label")
            tb.insert("end", f"{msg.plaintext}\n", "sent_text")
            tb.insert("end", f"  ╰─ {msg.ciphertext}\n", "cipher_text")
        else:
            tb.insert("end", f"[{msg.timestamp}] ", "timestamp")
            tb.insert("end", f"{self.contact_name}: ", "recv_label")
            tb.insert("end", f"{msg.plaintext}\n", "recv_text")

        tb.insert("end", "\n")
        self.history.configure(state="disabled")
        if scroll:
            self.history.see("end")

    # ── Wysyłanie ───────────────────────────────────────────────

    def _send(self):
        text = self.msg_entry.get().strip()
        if not text:
            return
        try:
            cipher = self._enc.encrypt(self.contact_name, text)
        except Exception as e:
            self._show_error(f"Szyfrowanie nie powiodło się:\n{e}")
            return

        msg = Message(direction="out", plaintext=text, ciphertext=cipher)
        self._store.add_message(self.contact_name, msg)
        self._render_message(msg)
        self.msg_entry.delete(0, "end")

        # Schowek - automatyczne skopiowanie zaszyfrowanego tekstu
        self.clipboard_clear()
        self.clipboard_append(cipher)
        self._flash_send_btn()

    def _flash_send_btn(self):
        """Chwilowe potwierdzenie wysłania - zmiana koloru przycisku."""
        self._send_btn.configure(text="✓ Skopiowano!", fg_color="#1a6b3c")
        self.after(1800, lambda: self._send_btn.configure(text="Wyślij 🔒", fg_color=["#3B8ED0", "#1F6AA5"]))

    # ── Odbieranie (deszyfrowanie) ───────────────────────────────

    def _handle_decrypt(self, cipher_text: str):
        cipher_text = cipher_text.strip()
        if not cipher_text:
            return
        try:
            plaintext = self._enc.decrypt(self.contact_name, cipher_text)
        except Exception as e:
            self._show_error(f"Deszyfrowanie nie powiodło się:\n{e}")
            return

        msg = Message(direction="in", plaintext=plaintext, ciphertext=cipher_text)
        self._store.add_message(self.contact_name, msg)
        self._render_message(msg)
        self._receive_panel.clear()

    # ── Pomocnicze ──────────────────────────────────────────────

    def _show_error(self, text: str):
        tb = self.history._textbox
        self.history.configure(state="normal")
        tb.insert("end", f"❌ {text}\n\n", "timestamp")
        self.history.configure(state="disabled")
        self.history.see("end")

    def clear_history(self):
        self._store.clear_history(self.contact_name)
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        self.history.configure(state="disabled")

    def focus_input(self):
        self.msg_entry.focus()


# ─────────────────────────────────────────────────────────────────
# Sidebar z listą kontaktów
# ─────────────────────────────────────────────────────────────────
class ContactSidebar(ctk.CTkFrame):
    def __init__(self, parent, on_open_cb, on_add_cb, on_edit_cb, on_delete_cb):
        super().__init__(parent, width=220, corner_radius=0)
        self.pack_propagate(False)
        self._on_open = on_open_cb
        self._on_add = on_add_cb
        self._on_edit = on_edit_cb
        self._on_delete = on_delete_cb
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._active: str | None = None
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Kontakty", font=FONT_TITLE).pack(pady=(16, 8))

        self._list_frame = ctk.CTkScrollableFrame(self, label_text="")
        self._list_frame.pack(fill="both", expand=True, padx=6, pady=4)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=6, pady=8)
        ctk.CTkButton(btn_frame, text="+ Dodaj kontakt", command=self._on_add).pack(fill="x", pady=2)

    def refresh(self, contacts: list[str], active: str | None = None):
        # usuń stare przyciski
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._buttons.clear()

        for name in contacts:
            row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)

            btn = ctk.CTkButton(
                row, text=name, anchor="w",
                fg_color="#2a5298" if name == active else "transparent",
                text_color=("white" if name == active else ["gray10", "gray90"]),
                hover_color="#2a5298",
                command=lambda n=name: self._on_open(n),
            )
            btn.pack(side="left", fill="x", expand=True)

            menu_btn = ctk.CTkButton(row, text="⋮", width=28, fg_color="transparent",
                                      hover_color="#444",
                                      command=lambda n=name: self._show_menu(n))
            menu_btn.pack(side="right")
            self._buttons[name] = btn

        self._active = active

    def set_active(self, name: str | None):
        self._active = name
        for n, btn in self._buttons.items():
            is_active = (n == name)
            btn.configure(
                fg_color="#2a5298" if is_active else "transparent",
                text_color="white" if is_active else ["gray10", "gray90"],
            )

    def _show_menu(self, name: str):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Otwórz rozmowę", command=lambda: self._on_open(name))
        menu.add_command(label="Edytuj kontakt",  command=lambda: self._on_edit(name))
        menu.add_separator()
        menu.add_command(label="Usuń kontakt",    command=lambda: self._on_delete(name))
        menu.tk_popup(*self.winfo_pointerxy())


# ─────────────────────────────────────────────────────────────────
# Główne okno aplikacji
# ─────────────────────────────────────────────────────────────────
class SimpleEncryptedChat(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("🔐 Hushbox - Encrypted Chat")
        self.geometry("1200x720")
        self.minsize(900, 580)

        self._enc = EncryptionManager(data_dir=DATA_DIR)
        self._store = ChatStore(data_dir=DATA_DIR)
        self._tabs: dict[str, ChatTab] = {}     # kontakt → zakładka

        self._build_layout()
        self._refresh_contacts()

    # ── Budowa layoutu ───────────────────────────────────────────

    def _build_layout(self):
        # Górny pasek z informacjami
        top_bar = ctk.CTkFrame(self, height=42, corner_radius=0, fg_color="#1a1a2e")
        top_bar.pack(fill="x")
        top_bar.pack_propagate(False)

        ctk.CTkLabel(top_bar, text="🔐 Hushbox - Encrypted Chat",
                     font=FONT_TITLE, text_color="white").pack(side="left", padx=16)

        my_key_btn = ctk.CTkButton(top_bar, text="📱 Mój QR", width=100,
                                    fg_color="#2a5298", command=self._show_qr)
        my_key_btn.pack(side="right", padx=6, pady=4)

        import_btn = ctk.CTkButton(top_bar, text="📷 Importuj QR", width=130,
                                    fg_color="#555", command=self._import_qr_key)
        import_btn.pack(side="right", padx=2, pady=4)

        # Główna zawartość
        body = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # Sidebar
        self._sidebar = ContactSidebar(
            body,
            on_open_cb=self._open_chat,
            on_add_cb=self._add_contact,
            on_edit_cb=self._edit_contact,
            on_delete_cb=self._delete_contact,
        )
        self._sidebar.pack(side="left", fill="y")

        # Obszar zakładek
        self._tab_area = ctk.CTkFrame(body, fg_color="transparent")
        self._tab_area.pack(side="left", fill="both", expand=True)

        self._notebook = ctk.CTkTabview(self._tab_area)
        self._notebook.pack(fill="both", expand=True, padx=6, pady=6)

        # Strona powitalna (gdy brak otwartych czatów)
        self._welcome = ctk.CTkFrame(self._tab_area, fg_color="transparent")
        ctk.CTkLabel(
            self._welcome,
            text="Wybierz kontakt, aby rozpocząć rozmowę\nlub dodaj nowy za pomocą przycisku '+ Dodaj kontakt'.",
            font=FONT_LABEL,
            justify="center",
        ).pack(expand=True)
        self._welcome.pack(fill="both", expand=True)
        self._notebook.pack_forget()

    # ── Kontakty ─────────────────────────────────────────────────

    def _refresh_contacts(self, active: str | None = None):
        contacts = self._enc.list_contacts()
        self._sidebar.refresh(contacts, active=active or self._current_contact())

    def _current_contact(self) -> str | None:
        try:
            return self._notebook.get()
        except Exception:
            return None

    def _add_contact(self):
        dlg = ContactDialog(self, title="Dodaj kontakt")
        self.wait_window(dlg)
        if dlg.result:
            name, key = dlg.result
            try:
                self._enc.add_contact(name, key)
                self._refresh_contacts()
                self._open_chat(name)
            except Exception as e:
                messagebox.showerror("Błąd", str(e), parent=self)

    def _edit_contact(self, name: str):
        dlg = ContactDialog(self, title="Edytuj kontakt",
                             name=name, key=self._enc.contact_keys.get(name, ""))
        self.wait_window(dlg)
        if dlg.result:
            new_name, new_key = dlg.result
            try:
                if new_name != name:
                    self._enc.rename_contact(name, new_name)
                    # przesuń historię
                    self._store.load(name)
                    old_path = self._store._path(name)
                    new_path = self._store._path(new_name)
                    if old_path.exists():
                        old_path.rename(new_path)
                    # zamknij starą zakładkę
                    self._close_tab(name)
                    name = new_name
                self._enc.add_contact(name, new_key)
                self._refresh_contacts()
                self._open_chat(name)
            except Exception as e:
                messagebox.showerror("Błąd", str(e), parent=self)

    def _delete_contact(self, name: str):
        if not messagebox.askyesno(
            "Usuń kontakt",
            f"Czy na pewno chcesz usunąć kontakt '{name}'?\n"
            "Historia rozmowy zostanie zachowana.",
            parent=self,
        ):
            return
        try:
            self._enc.remove_contact(name)
            self._close_tab(name)
            self._refresh_contacts()
        except Exception as e:
            messagebox.showerror("Błąd", str(e), parent=self)

    # ── Zakładki czatu ────────────────────────────────────────────

    def _open_chat(self, name: str):
        # Ukryj welcome screen, pokaż notebook
        self._welcome.pack_forget()
        self._notebook.pack(fill="both", expand=True, padx=6, pady=6)

        if name not in self._tabs:
            self._notebook.add(name)
            tab_frame = self._notebook.tab(name)
            chat_tab = ChatTab(tab_frame, name, self._enc, self._store)
            chat_tab.pack(fill="both", expand=True)
            self._tabs[name] = chat_tab

        self._notebook.set(name)
        self._sidebar.set_active(name)
        self._tabs[name].focus_input()

    def _close_tab(self, name: str):
        if name in self._tabs:
            try:
                self._notebook.delete(name)
            except Exception:
                pass
            del self._tabs[name]
        if not self._tabs:
            self._notebook.pack_forget()
            self._welcome.pack(fill="both", expand=True)

    # ── QR ───────────────────────────────────────────────────────

    def _show_qr(self):
        QRWindow(self, self._enc.export_public_key())

    def _import_qr_key(self):
        """Import klucza ze schowka (skopiowanego JSON lub surowego base64)."""
        raw = self.clipboard_get().strip() if self._clipboard_has_text() else ""
        if not raw:
            messagebox.showinfo(
                "Import klucza",
                "Skopiuj do schowka klucz publiczny (base64 lub JSON z QR kodu),\n"
                "a następnie kliknij ten przycisk ponownie.",
                parent=self,
            )
            return

        # Próbuj JSON
        public_key = None
        try:
            data = json.loads(raw)
            public_key = data.get("public_key", "")
        except Exception:
            public_key = raw  # traktuj jako surowy base64

        dlg = ContactDialog(self, title="Dodaj kontakt z QR", key=public_key)
        self.wait_window(dlg)
        if dlg.result:
            name, key = dlg.result
            try:
                self._enc.add_contact(name, key)
                self._refresh_contacts()
                self._open_chat(name)
            except Exception as e:
                messagebox.showerror("Błąd", str(e), parent=self)

    def _clipboard_has_text(self) -> bool:
        try:
            self.clipboard_get()
            return True
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────
# Uruchomienie
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = SimpleEncryptedChat()
    app.mainloop()
