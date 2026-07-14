import asyncio
import websockets
import json
import threading
import time
import logging
import queue
import argparse

parser = argparse.ArgumentParser(description="Tutor-Me")
parser.add_argument('--no-vision', action='store_true', help="Disable vision modality")
parser.add_argument('--model', type=str, default="gemma4:e4b", help="Model to use for Ollama")
args, _ = parser.parse_known_args()

logging.getLogger("websockets").setLevel(logging.CRITICAL)

from state_manager import StateManager
from warden import Warden
from desktop_sensor import DesktopSensor
from webcam_sensor import WebcamSensor
from ui import SetupUI, DashboardUI
import database
import customtkinter as ctk

state = StateManager()
warden = Warden(
    voice_style=state.state.settings.voice_style,
    support_vision=not args.no_vision,
    model_name=args.model
)
desktop = DesktopSensor()
webcam = WebcamSensor()

app = None
loop = None
root = None
ui_queue = queue.Queue()

def run_async_in_background(coro):
    if loop:
        asyncio.run_coroutine_threadsafe(coro, loop)

def on_setup_submit(goal):
    print("--- State 2: Generating Curriculum ---")
    def _generate():
        tasks = warden.generate_curriculum(goal)
        database.save_curriculum(goal, tasks)
        print("--- Curriculum saved ---")
        run_async_in_background(warden.speak_text("Queue generated. Press Start when ready."))
        ui_queue.put(transition_to_dashboard)
    
    threading.Thread(target=_generate, daemon=True).start()

def on_update_goal(goal):
    print(f"--- Appending to Curriculum: {goal} ---")
    if app:
        app.set_task_text("Generating additional curriculum...")
        app.update_queue([])
        
    def _generate():
        try:
            tasks = warden.generate_curriculum(goal)
            if not tasks:
                print("--- Generation returned empty tasks ---")
                run_async_in_background(warden.speak_text("I couldn't generate tasks. Please try again."))
                ui_queue.put(update_dashboard_task)
                return
                
            database.append_tasks_to_active_curriculum(goal, tasks)
            print("--- Tasks appended ---")
            run_async_in_background(warden.speak_text("New tasks added to the queue. Ready to conquer."))
            ui_queue.put(update_dashboard_task)
        except Exception as e:
            print(f"Error in background generation: {e}")
            ui_queue.put(update_dashboard_task)
    
    threading.Thread(target=_generate, daemon=True).start()

def transition_to_dashboard():
    global app
    if app:
        app.destroy()
    app = DashboardUI(root, on_session_start, on_session_done, on_queue_task_done, on_update_goal, on_pin_task, on_add_task)
    database.run_midnight_reset()
    update_dashboard_task()

def update_dashboard_task():
    task = database.get_next_incomplete_task()
    queue_list = database.get_upcoming_queue()
    
    if task:
        prefix = "[Daily] " if task.get("is_daily_habit") else ""
        app.set_task_text(f"{prefix}{task['task_title']}")
        
        # Display the rest of the queue
        app.update_queue(queue_list[1:])
    else:
        app.set_task_text("All tasks complete for now!")
        app.update_queue([])

def on_session_start(focus_style):
    print(f"--- State 3: Active Session Started ({focus_style}) ---")
    database.run_midnight_reset()
    update_dashboard_task()
    task = database.get_next_incomplete_task()
    if task:
        state.set_active_task(task)
        state.grace_period_start = None
        state.focus_style = focus_style
        if focus_style == "pomodoro":
            state.pomodoro_start_time = time.time()
        else:
            state.pomodoro_start_time = None
            
        # Overdue Nudge Logic
        if not task.get("is_daily_habit") and task.get("target_completion_date"):
            try:
                from datetime import datetime, timezone
                target_dt = datetime.fromisoformat(task["target_completion_date"].replace('Z', '+00:00'))
                if target_dt.tzinfo is None:
                    target_dt = target_dt.replace(tzinfo=timezone.utc)
                target_local = target_dt.astimezone().date()
                today_local = datetime.now().astimezone().date()
                days_left = (target_local - today_local).days
                
                if days_left < 0:
                    run_async_in_background(warden.speak_text(f"We are behind on {task['task_title']}. Let's lock in and clear it off the board."))
            except Exception as e:
                print(f"Error calculating days left for nudge: {e}")
                
    else:
        run_async_in_background(warden.speak_text("You have no incomplete tasks."))

def on_session_done():
    print("--- State 5: Flow Chainer ---")
    state.pomodoro_start_time = None
    if state.active_task:
        database.mark_task_complete(state.active_task["id"])
        state.active_task = None
        state.app_mode = "break"
    
    database.run_midnight_reset()
    task = database.get_next_incomplete_task()
    queue_list = database.get_upcoming_queue()
    
    if task:
        app.deiconify()
        app.set_task_text("Break Time! 05:00")
        app.update_queue(queue_list)
        run_async_in_background(warden.speak_text("Great job. Take a break."))
        
        def _break_countdown():
            for remaining in range(300, 0, -1):
                mins, secs = divmod(remaining, 60)
                ui_queue.put(lambda t=f"Break Time! {mins:02d}:{secs:02d}": app.set_task_text(t))
                time.sleep(1)
            
            prefix = "[Daily] " if task.get("is_daily_habit") else ""
            title = f"{prefix}{task['task_title']}"
            
            ui_queue.put(lambda: app.set_task_text(title))
            ui_queue.put(lambda: app.update_queue(queue_list[1:]))
            
            run_async_in_background(warden.speak_text(f"Break over. Starting {title}."))
            
            # Auto resume
            ui_queue.put(lambda: app._start())
            
        threading.Thread(target=_break_countdown, daemon=True).start()
    else:
        app.set_task_text("All tasks complete!")
        app.update_queue([])
        run_async_in_background(warden.speak_text("You are done for the day."))
        state.app_mode = "dashboard"

def on_queue_task_done(task_id):
    database.mark_task_complete(task_id)
    update_dashboard_task()

def on_pin_task(task_id):
    database.pin_task(task_id)
    update_dashboard_task()

def on_add_task(task_title: str, target_completion_date: str, is_daily_habit: bool = False):
    database.add_manual_task(task_title, target_completion_date, is_daily_habit)
    update_dashboard_task()

def trigger_pomodoro_break():
    if app:
        app.deiconify()
        app.set_task_text("Pomodoro Break! 05:00")
        app.start_btn.configure(state="disabled")
        app.done_btn.configure(state="disabled")
        for child in app.style_frame.winfo_children():
            child.configure(state="disabled")
            
    run_async_in_background(warden.speak_text("Pomodoro cycle complete. Take a 5 minute break."))
    
    def _break_countdown():
        for remaining in range(300, 0, -1):
            if getattr(state, "app_mode", None) != "break":
                return
            mins, secs = divmod(remaining, 60)
            ui_queue.put(lambda t=f"Pomodoro Break! {mins:02d}:{secs:02d}": app.set_task_text(t) if app else None)
            time.sleep(1)
            
        if getattr(state, "app_mode", None) != "break":
            return
            
        if state.active_task:
            prefix = "[Daily] " if state.active_task.get("is_daily_habit") else ""
            title = f"{prefix}{state.active_task['task_title']}"
            ui_queue.put(lambda: app.set_task_text(title) if app else None)
            
        run_async_in_background(warden.speak_text("Break over. Let's resume focus."))
        
        # Auto resume
        ui_queue.put(lambda: app._start() if app else None)
        
    threading.Thread(target=_break_countdown, daemon=True).start()



async def websocket_handler(websocket, path=None):
    print(f"--- WS Connection established from browser ---")
    async for message in websocket:
        try:
            data = json.loads(message)
            msg_type = data.get('type', 'UNKNOWN')
            url = data.get('url', 'unknown url')
            
            if data['type'] in ("THIN_PAYLOAD", "FAT_PAYLOAD"):
                text = data.get('text', '')
                title = data.get('title', '')
                url = data.get('url', '')
                eval_text = text if text else title
                app_name = url
                
                print(f"--- WS Message Received: {msg_type} from {app_name} ---")
                
                if state.app_mode == "focus":
                    await evaluate_context(eval_text, app_name, msg_type, websocket)
        except Exception as e:
            print(f"Error handling WS message: {e}")

async def pomodoro_loop():
    while True:
        await asyncio.sleep(5)
        if state.app_mode == "focus" and getattr(state, "focus_style", "continuous") == "pomodoro":
            if getattr(state, "pomodoro_start_time", None):
                elapsed = time.time() - state.pomodoro_start_time
                if elapsed >= 25 * 60:
                    state.app_mode = "break"
                    state.pomodoro_start_time = None
                    ui_queue.put(trigger_pomodoro_break)

async def desktop_loop():
    while True:
        task_info = state.active_task
        if state.app_mode == "focus" and task_info:
            text, desktop_imgs = await asyncio.to_thread(desktop.get_screen_text_and_segmented_images)
            task_info = state.active_task
            if task_info:
                is_distracted, reason = await asyncio.to_thread(warden.evaluate_desktop_state, task_info["task_title"], text, desktop_imgs)
                
                if is_distracted:
                    if not state.grace_period_start:
                        state.grace_period_start = time.time()
                        
                        async def enforce_grace_period():
                            await asyncio.sleep(15)
                            if state.grace_period_start and time.time() - state.grace_period_start >= 14:
                                t_info = state.active_task
                                if t_info:
                                    nudge = await asyncio.to_thread(
                                        warden.generate_intervention, 
                                        t_info["task_title"], 
                                        text, 
                                        None,
                                        t_info.get("date_added"),
                                        t_info.get("target_completion_date")
                                    )
                                    await warden.speak_text(nudge)
                                    state.grace_period_start = None
                        asyncio.create_task(enforce_grace_period())
        await asyncio.sleep(300)

async def physical_distraction_loop():
    while True:
        await asyncio.sleep(180)
        task_info = state.active_task
        if state.app_mode == "focus" and task_info:
            webcam_img = await asyncio.to_thread(webcam.get_snapshot_path)
            task_info = state.active_task
            if webcam_img and task_info:
                is_distracted, reason = await asyncio.to_thread(
                    warden.evaluate_physical_state, webcam_img, task_info["task_title"]
                )
                task_info = state.active_task
                if is_distracted and task_info:
                    nudge_text = await asyncio.to_thread(
                        warden.generate_intervention, 
                        task_info["task_title"], 
                        reason, 
                        webcam_img,
                        task_info.get("date_added"),
                        task_info.get("target_completion_date")
                    )
                    await warden.speak_text(nudge_text)

async def evaluate_context(text: str, app_name: str, msg_type: str = None, websocket = None):
    task_info = state.active_task
    if not task_info:
        return
        
    if app_name and app_name in state.known_links:
        status, reason = state.known_links[app_name]
        if status == "distracted":
            task_info = state.active_task
            if task_info:
                nudge = await asyncio.to_thread(
                    warden.generate_intervention, 
                    task_info["task_title"], 
                    text, 
                    None,
                    task_info.get("date_added"),
                    task_info.get("target_completion_date")
                )
                await warden.speak_text(nudge)
    else:
        status, reason = warden.check_keywords(text, state.allowed_software, [], app_name)
        
        if status == "ambiguous":
            if msg_type == "THIN_PAYLOAD" and websocket:
                await websocket.send(json.dumps({"command": "SCRAPE_DOM"}))
                return
                
            if len(text) > 200:
                task_info = state.active_task
                if task_info:
                    status, reason = await asyncio.to_thread(warden.evaluate_text_semantics, task_info["task_title"], text)
                
            if status == "ambiguous":
                desktop_img = await asyncio.to_thread(desktop.get_screenshot_path)
                webcam_img = await asyncio.to_thread(webcam.get_snapshot_path)
                task_info = state.active_task
                if task_info:
                    vision_status, vision_reason = await asyncio.to_thread(warden.evaluate_with_vision, task_info["task_title"], text, desktop_img, webcam_img)
                    
                    if vision_status in ["allowed", "distracted"]:
                        status = vision_status
                    else:
                        status = "allowed"
        
        if app_name and status in ["allowed", "distracted"]:
            state.known_links[app_name] = (status, "Cached result")

    if status == "distracted" and state.app_mode == "focus":
        if not state.grace_period_start:
            state.grace_period_start = time.time()
            async def enforce_grace_period():
                await asyncio.sleep(15)
                if state.grace_period_start and time.time() - state.grace_period_start >= 14:
                    webcam_img = await asyncio.to_thread(webcam.get_snapshot_path)
                    t_info = state.active_task
                    if t_info:
                        nudge = await asyncio.to_thread(
                            warden.generate_intervention, 
                            t_info["task_title"], 
                            text, 
                            None,
                            t_info.get("date_added"),
                            t_info.get("target_completion_date")
                        )
                        await warden.speak_text(nudge)
                    state.grace_period_start = None
            asyncio.create_task(enforce_grace_period())
    elif status == "allowed":
        state.grace_period_start = None

async def backend_main():
    import ssl
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain("cert.pem", "key.pem")
    
    ws_server = await websockets.serve(websocket_handler, "localhost", 8765, ssl=ssl_context)
    print("--- WebSocket Server listening on wss://localhost:8765 ---")
    await asyncio.gather(
        pomodoro_loop(),
        desktop_loop(),
        physical_distraction_loop(),
        ws_server.wait_closed()
    )

def start_backend():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(backend_main())

def poll_ui_queue():
    while not ui_queue.empty():
        func = ui_queue.get()
        try:
            func()
        except Exception as e:
            print(f"Error in UI queue execution: {e}")
    if root:
        root.after(100, poll_ui_queue)

if __name__ == "__main__":
    database.initialize_db()
    curr = database.get_active_curriculum()
    
    root = ctk.CTk()
    root.withdraw()
    
    if curr:
        database.run_midnight_reset()
        app = DashboardUI(root, on_session_start, on_session_done, on_queue_task_done, on_update_goal, on_pin_task, on_add_task)
        update_dashboard_task()
    else:
        app = SetupUI(root, on_setup_submit)
        
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()
    
    if root:
        root.after(100, poll_ui_queue)
        root.mainloop()
