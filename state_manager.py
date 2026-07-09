import json
import os
from pydantic import BaseModel
from typing import List, Optional
import database

CONFIG_FILE = "config.json"

class Settings(BaseModel):
    tts_url: str = "http://localhost:5050/v1/audio/speech" # Example OpenAI compatible endpoint

class AppState(BaseModel):
    settings: Settings = Settings()

class StateManager:
    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = config_path
        self.state = self.load_state()
        
        # Volatile session state
        self.active_task: Optional[dict] = None
        self.allowed_software: List[str] = []
        self.grace_period_start: Optional[float] = None
        self.known_links: dict = {}
        self.app_mode: str = "init" # "init", "setup", "dashboard", "focus", "break"
        
        # Ensure DB is initialized
        database.initialize_db()

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

    def set_active_task(self, task: dict):
        self.active_task = task
        self.allowed_software = task.get("allowed_software", [])
        self.app_mode = "focus"
        self.known_links = {}
