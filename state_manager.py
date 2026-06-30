import json
import os
from pydantic import BaseModel
from typing import List, Optional

CONFIG_FILE = "config.json"

class PomodoroSettings(BaseModel):
    focus_duration_mins: int = 45
    break_duration_mins: int = 15
    long_break_duration_mins: int = 30
    cycles_before_long_break: int = 3
    extension_mins: int = 5

class Settings(BaseModel):
    tts_url: str = "http://localhost:5050/v1/audio/speech" # Example OpenAI compatible endpoint
    pomodoro: PomodoroSettings = PomodoroSettings()

class AppState(BaseModel):
    settings: Settings = Settings()
    approved_apps: List[str] = []
    approved_tabs: List[str] = []
    current_emotion: str = "neutral"

class StateManager:
    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = config_path
        self.state = self.load_state()
        
        # Volatile session state
        self.active_goal: Optional[str] = None
        self.allowed_keywords: List[str] = []
        self.is_distracted: bool = False
        self.pomodoro_mode: str = "setup" # "setup", "focus", "break", "long_break"
        self.pomodoro_end_time: float = 0.0
        self.current_cycle: int = 0
        self.grace_period_start: Optional[float] = None
        self.pacing_style: str = "Continuous Focus"
        self.focus_start_time: float = 0.0
        self.last_praise_time: float = 0.0
        self.known_links: dict = {}

    def load_state(self) -> AppState:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                    return AppState(**data)
            except Exception as e:
                print(f"Error loading config: {e}")
        return AppState()

    def save_state(self):
        try:
            with open(self.config_path, "w") as f:
                f.write(self.state.model_dump_json(indent=4))
        except Exception as e:
            print(f"Error saving config: {e}")

    def add_approved_app(self, app_name: str):
        if app_name not in self.state.approved_apps:
            self.state.approved_apps.append(app_name)
            self.save_state()

    def add_approved_tab(self, tab_title: str):
        if tab_title not in self.state.approved_tabs:
            self.state.approved_tabs.append(tab_title)
            self.save_state()

    def set_active_goal(self, goal: str, keywords: List[str]):
        self.active_goal = goal
        self.allowed_keywords = keywords
        self.pomodoro_mode = "focus"
        self.current_cycle = 1
        self.state.approved_apps = []
        self.state.approved_tabs = []
        self.known_links = {}
        self.save_state()

    def is_app_approved(self, app_name: str) -> bool:
        return app_name in self.state.approved_apps

    def is_tab_approved(self, tab_title: str) -> bool:
        return tab_title in self.state.approved_tabs
