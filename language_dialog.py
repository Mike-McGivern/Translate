"""
Language Selection Dialog
Shows on first launch to select GUI language
"""

import customtkinter as ctk


class LanguageSelectionDialog(ctk.CTkToplevel):
    """Language selection dialog"""

    def __init__(self, parent):
        super().__init__(parent)

        self.selected_language = None

        # Window setup
        self.title("Language Selection / Selección de Idioma / 言語選択")
        self.geometry("500x400")
        self.resizable(False, False)

        # Make modal
        self.transient(parent)
        self.grab_set()

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 400) // 2
        self.geometry(f"+{x}+{y}")

        # Prevent closing without selection
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.create_ui()

    def create_ui(self):
        """Create the UI"""

        # Title
        title = ctk.CTkLabel(
            self,
            text="Select your language\nSeleccione su idioma\n言語を選択",
            font=("Arial", 20, "bold"),
            justify="center"
        )
        title.pack(pady=30)

        # Language buttons container
        button_container = ctk.CTkFrame(self, fg_color="transparent")
        button_container.pack(expand=True, fill="both", padx=40, pady=20)

        # English
        en_button = ctk.CTkButton(
            button_container,
            text="🇺🇸 English",
            font=("Arial", 18, "bold"),
            height=70,
            fg_color="#0066cc",
            hover_color="#0088ff",
            command=lambda: self.select_language("en")
        )
        en_button.pack(fill="x", pady=10)

        # Spanish
        es_button = ctk.CTkButton(
            button_container,
            text="🇪🇸 Español",
            font=("Arial", 18, "bold"),
            height=70,
            fg_color="#cc0000",
            hover_color="#ff0000",
            command=lambda: self.select_language("es")
        )
        es_button.pack(fill="x", pady=10)

        # Japanese
        ja_button = ctk.CTkButton(
            button_container,
            text="🇯🇵 日本語",
            font=("Arial", 18, "bold"),
            height=70,
            fg_color="#cc0066",
            hover_color="#ff0088",
            command=lambda: self.select_language("ja")
        )
        ja_button.pack(fill="x", pady=10)

        # German
        de_button = ctk.CTkButton(
            button_container,
            text="🇩🇪 Deutsch",
            font=("Arial", 18, "bold"),
            height=70,
            fg_color="#0044aa",
            hover_color="#0066dd",
            command=lambda: self.select_language("de")
        )
        de_button.pack(fill="x", pady=10)

        # French
        fr_button = ctk.CTkButton(
            button_container,
            text="🇫🇷 Français",
            font=("Arial", 18, "bold"),
            height=70,
            fg_color="#002f8a",
            hover_color="#004fcc",
            command=lambda: self.select_language("fr")
        )
        fr_button.pack(fill="x", pady=10)

    def select_language(self, language_code: str):
        """Handle language selection"""
        self.selected_language = language_code
        self.destroy()

    def on_close(self):
        """Prevent closing without selection"""
        if self.selected_language is None:
            self.select_language("en")

    def get_language(self) -> str:
        """Get selected language (blocks until selection)"""
        self.wait_window()
        return self.selected_language or "en"
