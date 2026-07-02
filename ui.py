import customtkinter as ctk
from typing import Callable, List, Dict

class SetupUI(ctk.CTkToplevel):
    def __init__(self, master, on_submit: Callable[[str], None]):
        super().__init__(master)
        self.on_submit = on_submit
        self.title("TutorMe - Setup")
        self.geometry("800x400")
        
        self.setup_ui()
        
    def setup_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        main_frame.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(main_frame, text="What are we conquering? Dump your goals here.", font=("Arial", 24, "bold"))
        lbl.grid(row=0, column=0, pady=(40, 20))
        
        self.goal_entry = ctk.CTkTextbox(main_frame, width=600, height=150, font=("Arial", 16))
        self.goal_entry.grid(row=1, column=0, pady=10)
        
        submit_btn = ctk.CTkButton(main_frame, text="Generate Curriculum", font=("Arial", 18, "bold"), height=50, command=self._submit)
        submit_btn.grid(row=2, column=0, pady=30)
        
    def _submit(self):
        goal = self.goal_entry.get("1.0", "end-1c").strip()
        if not goal:
            return
            
        self.destroy()
        self.on_submit(goal)

class DashboardUI(ctk.CTkToplevel):
    def __init__(self, master, on_start: Callable, on_done: Callable, on_queue_task_done: Callable = None):
        super().__init__(master)
        self.on_start = on_start
        self.on_done = on_done
        self.on_queue_task_done = on_queue_task_done
        
        self.title("TutorMe - Daily Standup")
        self.geometry("600x700")
        
        # Up Next Section
        self.up_next_frame = ctk.CTkFrame(self)
        self.up_next_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(self.up_next_frame, text="UP NEXT", font=("Arial", 12, "bold"), text_color="gray").pack(pady=(10, 0))
        self.task_label = ctk.CTkLabel(self.up_next_frame, text="Loading...", font=("Arial", 18, "bold"), wraplength=350)
        self.task_label.pack(pady=(5, 10), padx=10)
        
        # Buttons
        self.btn_frame = ctk.CTkFrame(self.up_next_frame, fg_color="transparent")
        self.btn_frame.pack(pady=(0, 10))
        
        self.start_btn = ctk.CTkButton(self.btn_frame, text="Start Session", command=self._start)
        self.start_btn.pack(side="left", padx=10)
        
        self.done_btn = ctk.CTkButton(self.btn_frame, text="Done", command=self._done)
        self.done_btn.pack(side="left", padx=10)
        self.done_btn.configure(state="disabled")
        
        # Focus Style
        self.focus_style_var = ctk.StringVar(value="continuous")
        self.style_frame = ctk.CTkFrame(self.up_next_frame, fg_color="transparent")
        self.style_frame.pack(pady=(0, 10))
        ctk.CTkRadioButton(self.style_frame, text="Continuous", variable=self.focus_style_var, value="continuous").pack(side="left", padx=10)
        ctk.CTkRadioButton(self.style_frame, text="Pomodoro (25m)", variable=self.focus_style_var, value="pomodoro").pack(side="left", padx=10)
        
        # Upcoming Queue Section
        ctk.CTkLabel(self, text="UPCOMING QUEUE", font=("Arial", 12, "bold"), text_color="gray").pack(pady=(10, 5), anchor="w", padx=20)
        
        self.queue_frame = ctk.CTkScrollableFrame(self)
        self.queue_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.queue_labels = []

    def set_task_text(self, text: str):
        self.task_label.configure(text=text)
        
    def update_queue(self, queue: list):
        # Clear existing
        for lbl in self.queue_labels:
            lbl.destroy()
        self.queue_labels.clear()
        
        if not queue:
            lbl = ctk.CTkLabel(self.queue_frame, text="Queue is empty.", text_color="gray")
            lbl.pack(pady=10)
            self.queue_labels.append(lbl)
            return
            
        for i, task in enumerate(queue):
            if task.get("is_daily_habit"):
                title = f"[Daily] {task.get('task_title', 'Unknown Task')}"
                color = "gray"
            else:
                title = task.get('task_title', 'Unknown Task')
                color = "gray"
                if task.get("target_completion_date"):
                    try:
                        from datetime import datetime, timezone
                        target_dt = datetime.fromisoformat(task["target_completion_date"].replace('Z', '+00:00'))
                        if target_dt.tzinfo is None:
                            target_dt = target_dt.replace(tzinfo=timezone.utc)
                        target_local = target_dt.astimezone().date()
                        today_local = datetime.now().astimezone().date()
                        days_left = (target_local - today_local).days
                        
                        if days_left < 0:
                            title = f"(OVERDUE) {title}"
                            color = "red"
                        elif days_left == 0:
                            title = f"(Due Today) {title}"
                            color = "orange"
                        else:
                            title = f"({days_left} Days Left) {title}"
                    except Exception as e:
                        print(f"Error parsing date for UI: {e}")
                        
            row_frame = ctk.CTkFrame(self.queue_frame, fg_color="transparent")
            row_frame.pack(fill="x", padx=5, pady=2)
            self.queue_labels.append(row_frame)
            
            lbl = ctk.CTkLabel(row_frame, text=title, text_color=color, anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            
            if self.on_queue_task_done:
                btn = ctk.CTkButton(row_frame, text="✓", width=30, height=24, command=lambda t_id=task["id"]: self.on_queue_task_done(t_id))
                btn.pack(side="right", padx=(5, 0))

    def _start(self):
        self.iconify()
        self.start_btn.configure(state="disabled")
        self.done_btn.configure(state="normal")
        # Disable style selection while running
        for child in self.style_frame.winfo_children():
            child.configure(state="disabled")
        self.on_start(self.focus_style_var.get())
        
    def _done(self):
        self.done_btn.configure(state="disabled")
        self.on_done()
        
    def reset_buttons(self):
        self.start_btn.configure(state="normal")
        self.done_btn.configure(state="disabled")
        for child in self.style_frame.winfo_children():
            child.configure(state="normal")
