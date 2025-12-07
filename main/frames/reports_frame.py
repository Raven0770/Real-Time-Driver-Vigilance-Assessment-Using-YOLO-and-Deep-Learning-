# frames/reports_frame.py
import os
import customtkinter as ctk
from tkinter import scrolledtext, filedialog, messagebox
from utils.file_utils import list_report_files, delete_file
import config
import datetime

class ReportsFrame(ctk.CTkFrame):
    def __init__(self, parent, reports_dir=config.REPORT_DIR):
        super().__init__(parent)
        self.reports_dir = reports_dir
        self.current_selected = None

        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=8, pady=(8,6))
        ctk.CTkLabel(top, text="Trip Summaries", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        actions = ctk.CTkFrame(top)
        actions.pack(side="right")
        ctk.CTkButton(actions, text="Refresh", command=self.refresh_files, width=90).pack(side="left", padx=6)
        ctk.CTkButton(actions, text="Export Selected", command=self.export_selected, width=120).pack(side="left", padx=6)
        ctk.CTkButton(actions, text="Delete Selected", command=self.delete_selected, width=120).pack(side="left", padx=6)

        split = ctk.CTkFrame(self)
        split.pack(fill="both", expand=True, padx=8, pady=6)
        left = ctk.CTkFrame(split, width=360)
        left.pack(side="left", fill="y", padx=(0,8), pady=4)
        left.pack_propagate(False)

        right = ctk.CTkFrame(split)
        right.pack(side="right", fill="both", expand=True, pady=4)

        self.list_scroll = ctk.CTkScrollableFrame(left)
        self.list_scroll.pack(fill="both", expand=True, padx=6, pady=6)
        self.card_buttons = []

        preview_card = ctk.CTkFrame(right)
        preview_card.pack(fill="both", expand=True, padx=6, pady=6)
        ctk.CTkLabel(preview_card, text="Preview", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=8, pady=(8,6))
        self.viewer = scrolledtext.ScrolledText(preview_card, wrap="word", font=("Consolas", 11), height=20)
        self.viewer.pack(fill="both", expand=True, padx=8, pady=(0,8))

        self.refresh_files()

    def refresh_files(self):
        for w in self.card_buttons:
            try:
                w.destroy()
            except Exception:
                pass
        self.card_buttons = []
        self.current_selected = None
        self.viewer.delete("1.0", "end")

        files = list_report_files(self.reports_dir)
        if not files:
            lbl = ctk.CTkLabel(self.list_scroll, text="(no reports)")
            lbl.pack(padx=6, pady=8)
            self.card_buttons.append(lbl)
            return

        for f in files:
            path = os.path.join(self.reports_dir, f)
            card = ctk.CTkFrame(self.list_scroll)
            card.pack(fill="x", padx=8, pady=6)
            title = ctk.CTkLabel(card, text=f, anchor="w", font=ctk.CTkFont(size=11, weight="bold"))
            title.pack(fill="x", padx=8, pady=(8,4))
            try:
                mtime = os.path.getmtime(path)
                meta = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            except Exception:
                meta = ""
            ctk.CTkLabel(card, text=meta, anchor="w").pack(fill="x", padx=8, pady=(0,8))
            btn_frame = ctk.CTkFrame(card)
            btn_frame.pack(fill="x", pady=(0,8), padx=8)
            ctk.CTkButton(btn_frame, text="Open", width=80, command=lambda fn=f: self.on_select(fn)).pack(side="left")
            ctk.CTkButton(btn_frame, text="Delete", width=80, command=lambda fn=f: self._delete_confirm(fn)).pack(side="right")
            self.card_buttons.append(card)

    def on_select(self, filename):
        self.current_selected = filename
        path = os.path.join(self.reports_dir, filename)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except Exception as e:
            text = f"Error reading file: {e}"
        self.viewer.delete("1.0", "end")
        self.viewer.insert("1.0", text)

    def _delete_confirm(self, filename):
        res = messagebox.askyesno("Confirm Delete", f"Delete report:\n\n{filename}? This is permanent.")
        if not res:
            return
        path = os.path.join(self.reports_dir, filename)
        ok = delete_file(path)
        if ok:
            messagebox.showinfo("Deleted", f"Deleted {filename}")
        else:
            messagebox.showwarning("Delete Failed", f"Could not delete {filename}")
        self.refresh_files()

    def delete_selected(self):
        if not self.current_selected:
            messagebox.showinfo("Delete Report", "No report selected.")
            return
        self._delete_confirm(self.current_selected)

    def export_selected(self):
        if not self.current_selected:
            messagebox.showinfo("Export", "No report selected.")
            return
        src = os.path.join(self.reports_dir, self.current_selected)
        dest = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=self.current_selected)
        if not dest:
            return
        try:
            with open(src, 'r', encoding='utf-8', errors='ignore') as s, open(dest, 'w', encoding='utf-8') as d:
                d.write(s.read())
            messagebox.showinfo("Exported", f"Saved to {dest}")
        except Exception as e:
            messagebox.showwarning("Export Failed", str(e))
