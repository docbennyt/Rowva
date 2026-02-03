# main.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import sqlite3
import json
import os
from datetime import datetime, timedelta

# Local modules
from parser import parse_whatsapp_day
from logic import validate_and_summarize
from db import save_daily_record, get_weekly_data, init_db, get_connection
from exporter import export_to_excel

# Initialize database on startup
init_db()

class RowvaMiniApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Rowva Mini 💰 — Offline Financial Assistant")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        
        # State
        self.current_view = "day"  # 'day', 'week', 'month'
        self.current_date = datetime.today().strftime('%Y-%m-%d')
        
        self.create_widgets()
        self.show_day_view()

    def create_widgets(self):
        # Top navigation bar
        nav_frame = ttk.Frame(self.root)
        nav_frame.pack(fill='x', padx=10, pady=5)
        
        self.btn_day = ttk.Button(nav_frame, text="📅 Day", command=self.show_day_view)
        self.btn_day.pack(side='left', padx=2)
        
        self.btn_week = ttk.Button(nav_frame, text="📆 Week", command=self.show_week_view)
        self.btn_week.pack(side='left', padx=2)
        
        self.btn_month = ttk.Button(nav_frame, text="📈 Month", command=self.show_month_view)
        self.btn_month.pack(side='left', padx=2)
        
        self.export_btn = ttk.Button(nav_frame, text="📤 Export Today", command=self.export_today)
        self.export_btn.pack(side='right')
        
        # Main content frame
        self.content_frame = ttk.Frame(self.root)
        self.content_frame.pack(fill='both', expand=True, padx=10, pady=5)

    def clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    # ================= DAY VIEW =================
    def show_day_view(self):
        self.current_view = "day"
        self.update_nav_buttons()
        self.clear_content()
        
        # Date auto-extracted from text — no manual entry!
        ttk.Label(self.content_frame, text="Paste WhatsApp Message:").pack(anchor='w')
        self.text_area = scrolledtext.ScrolledText(self.content_frame, height=8, font=("Consolas", 10))
        self.text_area.pack(fill='both', expand=True, pady=5)
        
        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="✅ Process & Save", command=self.process_day).pack(side='left')
        ttk.Button(btn_frame, text="📋 Process Clipboard", command=self.process_clipboard).pack(side='left', padx=(6,0))
        # Auto-process on paste toggle
        self.auto_paste_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btn_frame, text='Auto-process on paste', variable=self.auto_paste_var).pack(side='left', padx=(8,0))

        # Bind paste event to auto-process when enabled
        def on_paste(event=None):
            if self.auto_paste_var.get():
                try:
                    self.process_clipboard()
                    return "break"  # Prevent default paste behavior
                except Exception:
                    pass  # Allow normal paste if auto-process fails
            return None

        # Bind Control-V and Shift-Insert to on_paste
        self.text_area.bind('<Control-v>', lambda e: on_paste(e))
        self.text_area.bind('<Control-V>', lambda e: on_paste(e))
        self.text_area.bind('<Shift-Insert>', lambda e: on_paste(e))
        
        ttk.Label(self.content_frame, text="Structured Summary:").pack(anchor='w', pady=(10,0))
        self.output = scrolledtext.ScrolledText(self.content_frame, height=12, bg='#f9f9f9', state='disabled')
        self.output.pack(fill='both', expand=True)

    def process_day(self):
        raw_text = self.text_area.get("1.0", tk.END).strip()
        if not raw_text:
            messagebox.showwarning("Input Error", "Please paste a WhatsApp message.")
            return
            
        try:
            parsed = parse_whatsapp_day(raw_text)
            validated = validate_and_summarize(parsed)
            summary_text = validated['structured_text']

            # Save to DB (use original parsed dict, not validated)
            save_daily_record(parsed)
            self.current_date = parsed['date']

            # Show output (strict formatted summary)
            self.output.config(state='normal')
            self.output.delete("1.0", tk.END)
            self.output.insert("1.0", summary_text)
            self.output.config(state='disabled')

            # If there is an issue (variance), show a short warning dialog; else confirm save
            if validated.get('has_issue'):
                var = validated.get('variance')
                expected = validated.get('expected_cash')
                messagebox.showwarning("Variance detected",
                                       f"Variance: {var:+.2f}. Expected cash: {expected:.2f}. Please review the entry.")
            else:
                messagebox.showinfo("Success", f"Saved {parsed['date']}")

        except Exception as e:
            # Write full traceback to error log for diagnosis and put traceback on clipboard
            import traceback, os
            tb = traceback.format_exc()
            log_path = os.path.join(os.path.dirname(__file__), 'error.log')
            try:
                with open(log_path, 'a', encoding='utf-8') as f:
                    f.write(f"[{datetime.now().isoformat()}] Failed to process input:\n")
                    f.write(tb)
                    f.write('\n')
            except Exception:
                pass
            try:
                # copy traceback to clipboard for easier reporting
                self.root.clipboard_clear()
                self.root.clipboard_append(tb)
            except Exception:
                pass
            messagebox.showerror("Parse Error", f"Failed to process. Details written to {log_path}")

    def process_clipboard(self):
        try:
            clip = self.root.clipboard_get()
        except Exception:
            messagebox.showwarning('Clipboard', 'No text on clipboard')
            return
        # Paste into textarea and process
        self.text_area.delete('1.0', tk.END)
        self.text_area.insert('1.0', clip)
        self.process_day()
    def export_today(self):
        if self.current_view != "day":
            messagebox.showinfo("Note", "Export works from Day view after processing.")
            return
            
        raw_text = self.text_area.get("1.0", tk.END).strip()
        if not raw_text:
            messagebox.showwarning("Export", "No data to export.")
            return
            
        try:
            parsed = parse_whatsapp_day(raw_text)
            path = export_to_excel(parsed)
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    # ================= WEEK VIEW =================
    def show_week_view(self):
        self.current_view = "week"
        self.update_nav_buttons()
        self.clear_content()
        
        # Determine week start (Monday)
        dt = datetime.strptime(self.current_date, "%Y-%m-%d")
        week_start = dt - timedelta(days=dt.weekday())
        week_start_str = week_start.strftime("%Y-%m-%d")
        
        # Fetch data
        weekly_data = get_weekly_data(week_start_str)
        
        # Table
        cols = ("Date", "Day", "Income ($)", "Expenses ($)", "Cash ($)")
        tree = ttk.Treeview(self.content_frame, columns=cols, show='headings', height=8)
        
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=120, anchor='center')
        
        grand_income = grand_expenses = grand_cash = 0
        
        for date_iso, income, expenses, cash in weekly_data:
            dt_item = datetime.strptime(date_iso, "%Y-%m-%d")
            day_name = dt_item.strftime("%a")
            display_date = dt_item.strftime("%d %b")
            tree.insert("", "end", values=(
                display_date,
                day_name,
                f"{income:.2f}",
                f"{expenses:.2f}",
                f"{cash:.2f}"
            ))
            grand_income += income
            grand_expenses += expenses
            grand_cash += cash
        
        tree.pack(fill='both', expand=True, pady=5)
        
        # Grand totals
        total_frame = ttk.Frame(self.content_frame)
        total_frame.pack(fill='x', pady=5)
        ttk.Label(total_frame, text=f"TOTALS → Income: ${grand_income:.2f} | Expenses: ${grand_expenses:.2f} | Net Cash: ${grand_cash:.2f}", 
                  font=('TkDefaultFont', 10, 'bold')).pack(anchor='e')

    # ================= MONTH VIEW =================
    def show_month_view(self):
        self.current_view = "month"
        self.update_nav_buttons()
        self.clear_content()
        
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import matplotlib.pyplot as plt
        except ImportError:
            ttk.Label(self.content_frame, text="Install matplotlib for charts: pip install matplotlib", foreground="red").pack()
            return
        
        # Get current month data
        dt = datetime.strptime(self.current_date, "%Y-%m-%d")
        year, month = dt.year, dt.month
        
        conn = get_connection()
        c = conn.cursor()
        c.execute('''
            SELECT date, total_income, total_expenses
            FROM daily_records
            WHERE strftime('%Y-%m', date) = ?
            ORDER BY date
        ''', (f"{year}-{month:02d}",))
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            ttk.Label(self.content_frame, text="No data for this month yet.").pack()
            return
        
        dates = []
        incomes = []
        expenses = []
        
        for date_iso, inc, exp in rows:
            dt_item = datetime.strptime(date_iso, "%Y-%m-%d")
            dates.append(dt_item.strftime("%d"))
            incomes.append(inc)
            expenses.append(exp)
        
        # Plot
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(dates, incomes, marker='o', label='Income', color='#2E8B57')
        ax.plot(dates, expenses, marker='s', label='Expenses', color='#DC143C')
        ax.set_title(f"Cash Flow – {dt.strftime('%B %Y')}", fontsize=12)
        ax.set_ylabel("Amount ($)")
        ax.legend()
        ax.grid(True, linestyle='--', alpha=0.6)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, self.content_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)

    def update_nav_buttons(self):
        # Highlight active view
        for btn, view in [(self.btn_day, 'day'), (self.btn_week, 'week'), (self.btn_month, 'month')]:
            if self.current_view == view:
                btn.config(style='Accent.TButton')
            else:
                btn.config(style='TButton')

# Custom style for active button (optional)
def apply_custom_styles(root):
    style = ttk.Style()
    style.configure('Accent.TButton', background='#4CAF50', foreground='white')

if __name__ == "__main__":
    root = tk.Tk()
    apply_custom_styles(root)
    app = RowvaMiniApp(root)
    root.mainloop()