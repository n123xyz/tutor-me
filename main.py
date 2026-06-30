import asyncio
import websockets
import json
import threading
import time
import logging
import queue
import ollama

logging.getLogger("websockets").setLevel(logging.CRITICAL)

from state_manager import StateManager
from warden import Warden
from desktop_sensor import DesktopSensor
from webcam_sensor import WebcamSensor
from ui import TutorUI

state = StateManager()
warden = Warden(state.state.settings.tts_url)
desktop = DesktopSensor()
webcam = WebcamSensor()

app = None
loop = None
ui_queue = queue.Queue()

def on_goal_submit(goal: str, pacing: str):
    print(f"Goal received: {goal}")
    print(f"Pacing selected: {pacing}")
    
    def _parse_and_start():
        try:
            print("--- Background Thread: Starting to parse user goal ---")
            res = warden.parse_user_goal(goal)
            print(f"--- Background Thread: Successfully parsed goal: {res} ---")
            
            print("--- Background Thread: Setting active goal ---")
            state.set_active_goal(res.goal_summary, res.allowed_keywords)
            for app_name in res.allowed_applications:
                state.add_approved_app(app_name)
                
            state.pacing_style = pacing
            state.focus_start_time = time.time()
            state.last_praise_time = time.time()
            state.pomodoro_mode = "focus"
                
            print("--- Background Thread: Scheduling UI transition to minimal mode ---")
            ui_queue.put(lambda: app.minimal_mode("Focusing..."))
            print("--- Background Thread: Thread execution complete ---")
        except Exception as e:
            print(f"--- Background Thread: Error parsing goal: {e} ---")
            import traceback
            traceback.print_exc()
            ui_queue.put(lambda: app.submit_btn.configure(state="normal", text="Start Focus Session") if hasattr(app, "submit_btn") else None)
    
    threading.Thread(target=_parse_and_start, daemon=True).start()



async def websocket_handler(websocket, path=None):
    print("--- WebSocket: New client connected ---")
    async for message in websocket:
        try:
            data = json.loads(message)
            msg_type = data.get('type', 'UNKNOWN')
            url = data.get('url', 'unknown url')
            print(f"--- WebSocket: Received {msg_type} payload from {url} ---")
            
            if data['type'] in ("THIN_PAYLOAD", "FAT_PAYLOAD"):
                text = data.get('text', '')
                title = data.get('title', '')
                url = data.get('url', '')
                eval_text = text if text else title
                app_name = url
                
                if state.pomodoro_mode == "focus" and app.current_mode == "minimal":
                    await evaluate_context(eval_text, app_name, msg_type, websocket)
        except Exception as e:
            print(f"Error handling WS message: {e}")

async def desktop_loop():
    while True:
        if state.pomodoro_mode == "focus" and app.current_mode == "minimal":
            print("--- Desktop Loop: Running Desktop Vision Check ---")
            text, desktop_imgs = await asyncio.to_thread(desktop.get_screen_text_and_segmented_images)
            is_distracted, reason = await asyncio.to_thread(warden.evaluate_desktop_state, state.active_goal, text, desktop_imgs)
            
            if is_distracted:
                print(f"--- Desktop Loop: Distraction detected! Reason: {reason} ---")
                if not state.grace_period_start:
                    state.grace_period_start = time.time()
                    state.last_praise_time = time.time() # Reset praise clock
                    print(f"--- Desktop Distraction detected. Grace period started. ---")
                    
                    async def enforce_grace_period():
                        await asyncio.sleep(15)
                        if state.grace_period_start and time.time() - state.grace_period_start >= 14:
                            print(f"--- Grace period over. Triggering intervention. ---")
                            # Trigger intervention without passing emotion as it's just desktop distraction
                            nudge = await asyncio.to_thread(warden.generate_intervention, state.active_goal, text, None)
                            print(f"--- Intervention generated: {nudge} ---")
                            await warden.speak_text(nudge)
                            state.grace_period_start = None

                    asyncio.create_task(enforce_grace_period())
            else:
                print(f"--- Desktop Loop: User is focused on desktop. ({reason}) ---")
        await asyncio.sleep(300)



async def physical_distraction_loop():
    while True:
        await asyncio.sleep(180) # Every 3 minutes
        if state.pomodoro_mode == "focus" and app.current_mode == "minimal":
            print("--- Physical Distraction Loop: Running webcam check ---")
            webcam_img = await asyncio.to_thread(webcam.get_snapshot_path)
            if webcam_img:
                is_distracted, reason = await asyncio.to_thread(
                    warden.evaluate_physical_state, webcam_img, state.active_goal
                )
                if is_distracted:
                    print(f"--- Physical Distraction Loop: Distraction detected! Reason: {reason} ---")
                    state.last_praise_time = time.time() # Reset praise clock
                    # Generate and speak intervention
                    nudge_text = await asyncio.to_thread(
                        warden.generate_intervention, state.active_goal, reason, webcam_img
                    )
                    await warden.speak_text(nudge_text)
                else:
                    print(f"--- Physical Distraction Loop: User is focused. (Reason/Status: {reason}) ---")

async def evaluate_context(text: str, app_name: str, msg_type: str = None, websocket = None):
    
    if app_name and app_name in state.known_links:
        status, reason = state.known_links[app_name]
        if status == "distracted":
            nudge = await asyncio.to_thread(warden.generate_intervention, state.active_goal, text, None)
            await warden.speak_text(nudge)
        
        print(f"--- Warden: Cache Match for '{app_name}' returned '{status}' (Reason: {reason}) ---")
    else:
        status, reason = warden.check_keywords(text, state.allowed_keywords, state.state.approved_apps, app_name)
        print(f"--- Warden: Tier 1 Keyword Match for '{app_name}' returned '{status}' (Reason: {reason}) ---")
        
        if status == "ambiguous":
            if msg_type == "THIN_PAYLOAD" and websocket:
                print(f"--- Warden: '{app_name}' is ambiguous. Requesting FAT_PAYLOAD from browser extension ---")
                await websocket.send(json.dumps({"command": "SCRAPE_DOM"}))
                return
                
            if len(text) > 200:
                status, reason = await asyncio.to_thread(warden.evaluate_text_semantics, state.active_goal, text)
                print(f"--- Warden: Tier 1.5 Semantic Match returned '{status}' (Reason: {reason}) ---")
                
            if status == "ambiguous":
                print(f"--- Warden: '{app_name}' is ambiguous. Invoking Tier 2 Vision with webcam ---")
                desktop_img = await asyncio.to_thread(desktop.get_screenshot_path)
                webcam_img = await asyncio.to_thread(webcam.get_snapshot_path)
                vision_status, vision_reason = await asyncio.to_thread(warden.evaluate_with_vision, state.active_goal, text, desktop_img, webcam_img)
                print(f"--- Warden: Tier 2 Vision returned '{vision_status}' (Reason: {vision_reason}) ---")
                
                if vision_status == "allowed":
                    status = "allowed"
                elif vision_status == "distracted":
                    status = "distracted"
                else:
                    status = "allowed"
        
        if app_name and status in ["allowed", "distracted"]:
            state.known_links[app_name] = (status, "Cached result")

    if status == "distracted":
        if not state.grace_period_start:
            state.grace_period_start = time.time()
            state.last_praise_time = time.time() # Reset praise clock
            print(f"--- Distraction detected: {app_name}. Grace period started. ---")
            
            async def enforce_grace_period():
                await asyncio.sleep(15)
                if state.grace_period_start and time.time() - state.grace_period_start >= 14:
                    # Capture fresh webcam image
                    webcam_img = await asyncio.to_thread(webcam.get_snapshot_path)
                    
                    print(f"--- Grace period over. Triggering intervention. ---")
                    
                    # No need for a desktop screenshot, OCR text is sufficient for generating a nudge
                    nudge = await asyncio.to_thread(warden.generate_intervention, state.active_goal, text, None)
                    print(f"--- Intervention generated: {nudge} ---")
                    await warden.speak_text(nudge)
                    state.grace_period_start = None

            asyncio.create_task(enforce_grace_period())
    elif status == "allowed":
        if state.grace_period_start:
            print(f"--- Focus restored on {app_name}. Grace period reset. ---")
        state.grace_period_start = None

async def pomodoro_loop():
    while True:
        await asyncio.sleep(1)
        if state.pomodoro_mode == "focus" and app.current_mode == "minimal":
            now = time.time()
            elapsed_focus = now - state.focus_start_time
            elapsed_praise = now - state.last_praise_time
            
            # Praise check (every 10 minutes = 600 seconds)
            if elapsed_praise >= 600:
                print("--- Pomodoro Loop: User has been focused for 10 minutes. Generating praise. ---")
                state.last_praise_time = now # Reset immediately
                minutes = int(elapsed_focus // 60)
                praise = await asyncio.to_thread(warden.generate_praise, state.active_goal, minutes)
                print(f"--- Praise generated: {praise} ---")
                await warden.speak_text(praise)
                
            # Pomodoro check (25 minutes = 1500 seconds)
            if "Pomodoro" in state.pacing_style and elapsed_focus >= 1500:
                print("--- Pomodoro Loop: 25 minutes elapsed. Starting Break. ---")
                state.pomodoro_mode = "break"
                state.pomodoro_end_time = now + 300 # 5 minute break
                ui_queue.put(lambda: app.update_minimal_status("Break Time!", "5:00"))
                await warden.speak_text("You've been working hard for 25 minutes. Take a 5 minute break.")
        
        elif state.pomodoro_mode == "break" and app.current_mode == "minimal":
            now = time.time()
            remaining = state.pomodoro_end_time - now
            if remaining <= 0:
                print("--- Pomodoro Loop: Break over. Resuming Focus. ---")
                state.pomodoro_mode = "focus"
                state.focus_start_time = now
                state.last_praise_time = now
                ui_queue.put(lambda: app.update_minimal_status("Focusing...", "Session Active"))
                await warden.speak_text("Break's over! Let's get back to work.")
            else:
                mins, secs = divmod(int(remaining), 60)
                ui_queue.put(lambda: app.update_minimal_status("Break Time!", f"{mins:02d}:{secs:02d}"))

async def backend_main():
    import ssl
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain("cert.pem", "key.pem")
    
    ws_server = await websockets.serve(websocket_handler, "localhost", 8765, ssl=ssl_context)
    await asyncio.gather(
        desktop_loop(),
        pomodoro_loop(),
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
    app.after(100, poll_ui_queue)

if __name__ == "__main__":
    app = TutorUI(on_goal_submit)
    
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()
    
    app.after(100, poll_ui_queue)
    app.mainloop()
