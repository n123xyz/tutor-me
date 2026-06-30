import customtkinter as ctk
from typing import Callable, Optional

class TutorUI(ctk.CTk):
    def __init__(self, on_goal_submit: Callable[[str, str], None]):
        super().__init__()
        
        self.on_goal_submit = on_goal_submit
        
        self.title("AI Tutor Assistant")
        self.geometry("400x200")
        self.attributes("-topmost", True)
        
        self.current_mode = None
        self.setup_mode()

    def clear_window(self):
        for widget in self.winfo_children():
            widget.destroy()

    def setup_mode(self):
        self.clear_window()
        self.current_mode = "setup"
        self.geometry("500x300")
        self.attributes("-alpha", 1.0)
        self.overrideredirect(False)
        self.deiconify()
        
        lbl = ctk.CTkLabel(self, text="What is your goal for this session?", font=("Arial", 16, "bold"))
        lbl.pack(pady=(20, 10))
        
        self.goal_entry = ctk.CTkEntry(self, width=400, placeholder_text="I am working on [Task] using [Tools/Software]")
        self.goal_entry.pack(pady=10)
        
        self.pacing_var = ctk.StringVar(value="Continuous Focus")
        self.pacing_menu = ctk.CTkOptionMenu(self, variable=self.pacing_var, values=["Continuous Focus", "Pomodoro (25/5)"])
        self.pacing_menu.pack(pady=10)
        
        self.submit_btn = ctk.CTkButton(self, text="Start Focus Session", command=self._handle_goal_submit)
        self.submit_btn.pack(pady=20)

    def _handle_goal_submit(self):
        goal = self.goal_entry.get()
        pacing = self.pacing_var.get()
        if goal:
            self.submit_btn.configure(state="disabled", text="Parsing Goal... Please wait")
            self.on_goal_submit(goal, pacing)

    def minimal_mode(self, time_remaining: str = ""):
        print("--- UI: Transitioning to minimal mode (hidden) ---")
        self.current_mode = "minimal"
        self.iconify() # Minimize to standard taskbar

    def update_minimal_status(self, status_text: str, time_remaining: str):
        pass # UI is hidden, no need to update labels

if __name__ == "__main__":
    app = TutorUI(lambda g, p: print(f"Goal: {g}, Pacing: {p}"))
    app.mainloop()
