"""
Loading dialog for model downloads
"""

import customtkinter as ctk
import threading


class LoadingDialog(ctk.CTkToplevel):
    """Modal loading dialog"""

    def __init__(self, parent, title="Loading...", message="Please wait..."):
        super().__init__(parent)

        self.title(title)
        self.geometry("400x150")
        self.resizable(False, False)

        # Make modal
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 400) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 150) // 2
        self.geometry(f"+{x}+{y}")

        # Content
        self.message_label = ctk.CTkLabel(
            self,
            text=message,
            font=("Arial", 14)
        )
        self.message_label.pack(pady=20)

        # Progress bar
        self.progress = ctk.CTkProgressBar(self, width=300)
        self.progress.pack(pady=10)
        self.progress.set(0)

        # Start indeterminate by default
        self.indeterminate = True
        self.progress.configure(mode="indeterminate")
        self.progress.start()

        # Status label
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=("Arial", 11),
            text_color="#888888"
        )
        self.status_label.pack(pady=5)

        # Progress details (speed, size)
        self.details_label = ctk.CTkLabel(
            self,
            text="",
            font=("Arial", 10),
            text_color="#666666"
        )
        self.details_label.pack(pady=2)

    def update_message(self, message: str):
        """Update the message"""
        self.message_label.configure(text=message)

    def update_status(self, status: str):
        """Update status text"""
        self.status_label.configure(text=status)

    def update_progress(self, current: int, total: int, speed: float = 0):
        """Update progress bar with actual values

        Args:
            current: Bytes downloaded
            total: Total bytes
            speed: Download speed in bytes/sec
        """
        # Switch to determinate mode if needed
        if self.indeterminate:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.indeterminate = False

        # Update progress
        if total > 0:
            progress = current / total
            self.progress.set(progress)

            # Format sizes
            current_mb = current / (1024 * 1024)
            total_mb = total / (1024 * 1024)

            # Format speed
            if speed > 0:
                if speed > 1024 * 1024:  # > 1 MB/s
                    speed_str = f"{speed / (1024 * 1024):.1f} MB/s"
                else:
                    speed_str = f"{speed / 1024:.1f} KB/s"

                self.details_label.configure(
                    text=f"{current_mb:.1f} MB / {total_mb:.1f} MB  •  {speed_str}"
                )
            else:
                self.details_label.configure(
                    text=f"{current_mb:.1f} MB / {total_mb:.1f} MB"
                )

    def close(self):
        """Close the dialog"""
        if self.indeterminate:
            self.progress.stop()
        self.destroy()
