from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, filedialog, messagebox, ttk
import tkinter as tk

from .pdf_splitter import split_folder


class ShippingPdfSplitterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Shipping PDF Splitter")
        self.geometry("780x520")
        self.minsize(680, 420)

        self.selected_folder = tk.StringVar()
        self.status = tk.StringVar(value="Choose a folder containing shipping PDFs.")
        self._messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self._worker: threading.Thread | None = None

        self._build_widgets()
        self.after(100, self._drain_messages)

    def _build_widgets(self) -> None:
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill=BOTH, expand=True)

        ttk.Label(outer, text="Folder").pack(anchor="w")
        folder_row = ttk.Frame(outer)
        folder_row.pack(fill=X, pady=(4, 12))
        ttk.Entry(folder_row, textvariable=self.selected_folder).pack(side=LEFT, fill=X, expand=True)
        ttk.Button(folder_row, text="Browse...", command=self._browse_folder).pack(side=RIGHT, padx=(8, 0))

        action_row = ttk.Frame(outer)
        action_row.pack(fill=X, pady=(0, 12))
        self.split_button = ttk.Button(action_row, text="Split PDFs", command=self._start_split)
        self.split_button.pack(side=LEFT)
        self.progress = ttk.Progressbar(action_row, mode="indeterminate")
        self.progress.pack(side=LEFT, fill=X, expand=True, padx=(12, 0))

        ttk.Label(outer, textvariable=self.status).pack(anchor="w", pady=(0, 8))

        log_frame = ttk.LabelFrame(outer, text="Log", padding=8)
        log_frame.pack(fill=BOTH, expand=True)
        self.log = tk.Text(log_frame, height=16, wrap="word", state="disabled")
        self.log.pack(fill=BOTH, expand=True)

    def _browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose folder with PDF files")
        if folder:
            self.selected_folder.set(folder)
            self.status.set("Ready to split PDFs.")

    def _start_split(self) -> None:
        folder = Path(self.selected_folder.get()).expanduser()
        if not folder.is_dir():
            messagebox.showerror("Choose a folder", "Please choose a valid folder first.")
            return
        if self._worker and self._worker.is_alive():
            return

        self._set_running(True)
        self._write_log(f"Starting split for: {folder}")
        self._worker = threading.Thread(target=self._run_split, args=(folder,), daemon=True)
        self._worker.start()

    def _run_split(self, folder: Path) -> None:
        try:
            results = split_folder(folder, progress=self._queue_log)
        except Exception as exc:  # GUI boundary: show unexpected failures to the user.
            self._messages.put(("error", f"{exc}\n\n{traceback.format_exc()}"))
            return
        total_outputs = sum(len(result.output_files) for result in results)
        review_pages = sum(len(result.unmatched_pages) for result in results)
        output_dirs = {result.output_dir for result in results}
        self._messages.put(
            (
                "done",
                (
                    f"Done. Created {total_outputs} split PDF(s). "
                    f"{review_pages} page(s) need review.\n"
                    f"Output folder: {', '.join(str(path) for path in sorted(output_dirs))}"
                ),
            )
        )

    def _queue_log(self, message: str) -> None:
        self._messages.put(("log", message))

    def _drain_messages(self) -> None:
        while True:
            try:
                kind, message = self._messages.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self._write_log(message)
                self.status.set(message)
            elif kind == "done":
                self._write_log(message)
                self.status.set("Complete.")
                self._set_running(False)
                messagebox.showinfo("Shipping PDF Splitter", message)
            elif kind == "error":
                self._write_log(message)
                self.status.set("Error.")
                self._set_running(False)
                messagebox.showerror("Error splitting PDFs", message)

        self.after(100, self._drain_messages)

    def _set_running(self, running: bool) -> None:
        if running:
            self.split_button.configure(state="disabled")
            self.progress.start(10)
        else:
            self.progress.stop()
            self.split_button.configure(state="normal")

    def _write_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert(END, message + "\n")
        self.log.see(END)
        self.log.configure(state="disabled")


def main() -> None:
    app = ShippingPdfSplitterApp()
    app.mainloop()
