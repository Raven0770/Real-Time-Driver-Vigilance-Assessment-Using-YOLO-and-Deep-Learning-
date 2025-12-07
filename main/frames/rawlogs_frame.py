# frames/rawlogs_frame.py
import os
import pandas as pd
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
from utils.file_utils import list_log_files, delete_file
import config

class RawLogsFrame(ctk.CTkFrame):
    def __init__(self, parent, log_dir=config.LOG_DIR):
        super().__init__(parent)
        self.log_dir = log_dir

        top = ctk.CTkFrame(self)
        top.pack(fill="x", pady=(6,8), padx=6)

        ctk.CTkLabel(top, text="Raw Event Logs (.csv)", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        right = ctk.CTkFrame(top)
        right.pack(side="right")

        self.combo = ctk.CTkComboBox(right, values=[], command=self.on_select, width=300)
        self.combo.pack(side="left", padx=(0,6))
        self.refresh_btn = ctk.CTkButton(right, text="Refresh", width=80, command=self.refresh_files)
        self.refresh_btn.pack(side="left", padx=(0,6))
        self.delete_btn = ctk.CTkButton(right, text="Delete Selected", width=120, command=self.delete_selected)
        self.delete_btn.pack(side="left")

        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=6, pady=6)

        # native ttk Treeview for good performance
        self.tree = ttk.Treeview(table_frame, show="headings")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        self.tree.pack(side="top", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")

        self.refresh_files()

    def refresh_files(self):
        files = list_log_files(self.log_dir)
        if not files:
            files = []
        self.combo.configure(values=files)
        if files:
            self.combo.set(files[0])
            self.load_table(os.path.join(self.log_dir, files[0]))
        else:
            self.tree.delete(*self.tree.get_children())
            self.tree["columns"] = ()

    def on_select(self, value):
        if not value:
            return
        self.load_table(os.path.join(self.log_dir, value))

    def load_table(self, path):
        try:
            df = pd.read_csv(path)
        except Exception as e:
            self.tree.delete(*self.tree.get_children())
            self.tree["columns"] = ("Error",)
            self.tree.heading("Error", text=str(e))
            return

        max_cols = 12
        df = df.iloc[:, :max_cols]

        self.tree.delete(*self.tree.get_children())
        cols = list(df.columns)
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=120, anchor="w")

        for i, row in df.reset_index(drop=True).head(200).iterrows():
            vals = [str(row.get(c, "")) for c in cols]
            self.tree.insert("", "end", values=vals)

    def delete_selected(self):
        selected = self.combo.get()
        if not selected:
            messagebox.showinfo("Delete Log", "No log selected.")
            return
        path = os.path.join(self.log_dir, selected)
        res = messagebox.askyesno("Confirm Delete", f"Delete log:\n\n{selected}? This is permanent.")
        if not res:
            return
        ok = delete_file(path)
        if ok:
            messagebox.showinfo("Deleted", f"Deleted {selected}")
        else:
            messagebox.showwarning("Delete Failed", f"Could not delete {selected}")
        self.refresh_files()
