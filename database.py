import sqlite3
import json
from datetime import datetime, timezone
import os

DB_PATH = "tutorme.db"

def initialize_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Weekly Curriculum
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weekly_curriculum (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    
    # Study Tasks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            curriculum_id INTEGER NOT NULL,
            task_title TEXT NOT NULL,
            description TEXT,
            allowed_software TEXT NOT NULL,
            sequence_order INTEGER,
            is_daily_habit BOOLEAN DEFAULT 0,
            is_completed BOOLEAN DEFAULT 0,
            last_completed_date TEXT,
            date_added TEXT,
            target_completion_date TEXT,
            FOREIGN KEY (curriculum_id) REFERENCES weekly_curriculum(id)
        )
    """)
    
    conn.commit()
    conn.close()

def save_curriculum(goal: str, tasks: list):
    """
    tasks is a list of dicts:
    {
      "task_title": "string",
      "description": "string",
      "sequence_order": int,
      "is_daily_habit": bool,
      "days_allotted": int,
      "allowed_software": ["app1", "app2"]
    }
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now_utc = datetime.now(timezone.utc).isoformat()
    
    # Mark old ones inactive
    cursor.execute("UPDATE weekly_curriculum SET is_active = 0 WHERE is_active = 1")
    
    cursor.execute("INSERT INTO weekly_curriculum (goal, created_at, is_active) VALUES (?, ?, ?)", (goal, now_utc, 1))
    curriculum_id = cursor.lastrowid
    
    for t in tasks:
        days = t.get("days_allotted", 1)
        # default to 1 if empty or null
        if days is None:
            days = 1
            
        target_date = datetime.now(timezone.utc)
        import datetime as dt_lib
        target_date = target_date + dt_lib.timedelta(days=days)
        target_iso = target_date.isoformat()
        
        cursor.execute("""
            INSERT INTO study_tasks (curriculum_id, task_title, description, allowed_software, sequence_order, is_daily_habit, is_completed, last_completed_date, date_added, target_completion_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            curriculum_id, 
            t["task_title"], 
            t.get("description", ""), 
            json.dumps(t.get("allowed_software", [])), 
            t.get("sequence_order", None),
            1 if t.get("is_daily_habit", False) else 0,
            0, 
            None,
            now_utc,
            target_iso
        ))
        
    conn.commit()
    conn.commit()
    conn.close()

def append_tasks_to_active_curriculum(new_goal_text: str, tasks: list):
    curr = get_active_curriculum()
    if not curr:
        save_curriculum(new_goal_text, tasks)
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    updated_goal = curr["goal"] + "\n+ " + new_goal_text
    cursor.execute("UPDATE weekly_curriculum SET goal = ? WHERE id = ?", (updated_goal, curr["id"]))
    
    cursor.execute("SELECT MAX(sequence_order) FROM study_tasks WHERE curriculum_id = ?", (curr["id"],))
    row = cursor.fetchone()
    max_seq = row[0] if row and row[0] is not None else 0
    
    now_utc = datetime.now(timezone.utc).isoformat()
    
    for t in tasks:
        days = t.get("days_allotted", 1)
        if days is None:
            days = 1
            
        target_date = datetime.now(timezone.utc)
        import datetime as dt_lib
        target_date = target_date + dt_lib.timedelta(days=days)
        target_iso = target_date.isoformat()
        
        seq = t.get("sequence_order", None)
        if seq is not None:
            seq += max_seq
            
        cursor.execute("""
            INSERT INTO study_tasks (curriculum_id, task_title, description, allowed_software, sequence_order, is_daily_habit, is_completed, last_completed_date, date_added, target_completion_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            curr["id"], 
            t["task_title"], 
            t.get("description", ""), 
            json.dumps(t.get("allowed_software", [])), 
            seq,
            1 if t.get("is_daily_habit", False) else 0,
            0, 
            None,
            now_utc,
            target_iso
        ))
        
    conn.commit()
    conn.close()

def get_active_curriculum():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, goal FROM weekly_curriculum WHERE is_active = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "goal": row[1]}
    return None

def run_midnight_reset():
    curr = get_active_curriculum()
    if not curr:
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, last_completed_date
        FROM study_tasks
        WHERE curriculum_id = ? AND is_daily_habit = 1 AND is_completed = 1
    """, (curr["id"],))
    rows = cursor.fetchall()
    
    today_local = datetime.now().astimezone().date()
    
    to_reset = []
    for row_id, last_completed_iso in rows:
        if not last_completed_iso:
            to_reset.append(row_id)
            continue
            
        try:
            # Parse the UTC ISO string and convert to local date
            dt = datetime.fromisoformat(last_completed_iso.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            last_completed_local = dt.astimezone().date()
            
            if today_local > last_completed_local:
                to_reset.append(row_id)
        except Exception as e:
            print(f"Error parsing date {last_completed_iso}: {e}")
            to_reset.append(row_id)
            
    for task_id in to_reset:
        cursor.execute("UPDATE study_tasks SET is_completed = 0 WHERE id = ?", (task_id,))
        
    conn.commit()
    conn.close()

def get_next_incomplete_task():
    curr = get_active_curriculum()
    if not curr:
        return None
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Priority 1: Daily Habits
    cursor.execute("""
        SELECT id, task_title, description, allowed_software, sequence_order, is_daily_habit, date_added, target_completion_date
        FROM study_tasks 
        WHERE curriculum_id = ? AND is_completed = 0 AND is_daily_habit = 1
        ORDER BY id ASC LIMIT 1
    """, (curr["id"],))
    row = cursor.fetchone()
    
    # Priority 2: Sequential Tasks
    if not row:
        cursor.execute("""
            SELECT id, task_title, description, allowed_software, sequence_order, is_daily_habit, date_added, target_completion_date
            FROM study_tasks 
            WHERE curriculum_id = ? AND is_completed = 0 AND is_daily_habit = 0
            ORDER BY sequence_order ASC LIMIT 1
        """, (curr["id"],))
        row = cursor.fetchone()
        
    conn.close()
    
    if row:
        return {
            "id": row[0],
            "task_title": row[1],
            "description": row[2],
            "allowed_software": json.loads(row[3]),
            "sequence_order": row[4],
            "is_daily_habit": bool(row[5]),
            "date_added": row[6],
            "target_completion_date": row[7]
        }
    return None

def get_upcoming_queue():
    curr = get_active_curriculum()
    if not curr:
        return []
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all uncompleted tasks
    cursor.execute("""
        SELECT id, task_title, is_daily_habit, sequence_order, target_completion_date
        FROM study_tasks 
        WHERE curriculum_id = ? AND is_completed = 0
    """, (curr["id"],))
    rows = cursor.fetchall()
    conn.close()
    
    tasks = []
    for r in rows:
        tasks.append({
            "id": r[0],
            "task_title": r[1],
            "is_daily_habit": bool(r[2]),
            "sequence_order": r[3],
            "target_completion_date": r[4]
        })
        
    # Sort: Daily Habits first, then Sequential Tasks by sequence_order
    tasks.sort(key=lambda x: (not x["is_daily_habit"], x["sequence_order"] if x["sequence_order"] is not None else float('inf')))
    return tasks

def mark_task_complete(task_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_utc = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE study_tasks SET is_completed = 1, last_completed_date = ? WHERE id = ?", (now_utc, task_id))
    conn.commit()
    conn.close()
