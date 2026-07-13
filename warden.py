import json
from pydantic import BaseModel
from typing import List, Tuple, Optional
import ollama
from openai import OpenAI
import pygame
import asyncio
import os

class Warden:
    def __init__(self, tts_url: str):
        self.tts_url = tts_url
        self.model_name = "gemma4:e4b" # Change to specific model name as needed
        self.vision_client = ollama.Client(timeout=60.0)
        from openai import AsyncOpenAI
        base_url = self.tts_url
        if base_url.endswith("/v1/audio/speech"):
            base_url = base_url.replace("/audio/speech", "")
        self.tts_client = AsyncOpenAI(base_url=base_url, api_key="not-needed")
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"Pygame mixer init failed: {e}")

    def generate_curriculum(self, goal: str) -> list:
        schema = {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task_title": {"type": "string"},
                            "description": {"type": "string"},
                            "sequence_order": {"type": ["integer", "null"], "description": "Order of task. Null for daily habits."},
                            "is_daily_habit": {"type": "boolean"},
                            "days_allotted": {"type": ["integer", "null"], "description": "1 to 3 days to complete a non-daily task. Null if daily habit."},
                            "allowed_software": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["task_title", "description", "is_daily_habit", "allowed_software", "days_allotted"]
                    }
                }
            },
            "required": ["tasks"]
        }
        
        system_prompt = (
            "You are an AI Architect. The user wants to achieve this goal: " + goal + ". "
            "Break these goals down into a sequential queue of Study Tasks. Each task should take roughly 30 to 60 minutes. "
            "Identify 'Daily Habits' (set is_daily_habit=True and sequence_order=null, days_allotted=null). "
            "For one-off 'Sequential Tasks' (set is_daily_habit=False and assign a sequence_order 1, 2, 3...), assign a 'days_allotted' integer (between 1 and 3) representing how soon the user should complete this task to stay on track for the week. "
            "Output must strictly match this JSON schema."
        )
        
        user_prompt = f"Goal: {goal}"
        
        try:
            print(f"--- Warden: Generating curriculum with {self.model_name} ---")
            response = ollama.chat(model=self.model_name, messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], format=schema)
            
            data = json.loads(response['message']['content'])
            return data.get("tasks", [])
        except Exception as e:
            print(f"--- Warden: Failed to generate curriculum: {e} ---")
            import traceback
            traceback.print_exc()
            return []

    def check_keywords(self, text: str, allowed_keywords: List[str], allowed_apps: List[str], app_name: str) -> Tuple[str, str]:
        import re
        text_lower = text.lower()
        app_lower = app_name.lower()
        
        def matches_word(keyword, target_text):
            # Use word boundaries to prevent matching substrings inside larger words
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            return bool(re.search(pattern, target_text))
        
        # Check if the app itself is allowed
        for app in allowed_apps:
            if matches_word(app, app_lower):
                return "allowed", f"App matched allowed list: '{app}'"
                
        # Check if any allowed keywords are present in the OCR text or window title
        for kw in allowed_keywords:
            if matches_word(kw, text_lower) or matches_word(kw, app_lower):
                return "allowed", f"Keyword matched: '{kw}'"
                
        # Known distraction keywords (could be moved to config)
        distraction_keywords = ["netflix", "twitter", "facebook", "instagram", "tiktok"]
        for kw in distraction_keywords:
            if matches_word(kw, app_lower) or matches_word(kw, text_lower):
                return "distracted", f"Distraction keyword matched: '{kw}'"
                
        return "ambiguous", "No clear keyword matches found"

    def evaluate_text_semantics(self, goal: str, text: str) -> Tuple[str, str]:
        prompt = f"The user's goal is: '{goal}'. They are looking at a screen containing this text: '{text[:1500]}'. Is this content related to their goal, or are they distracted? Reply with ONLY a valid JSON object: {{\"status\": \"distracted\" | \"allowed\", \"reason\": \"short explanation\"}}"
        
        try:
            response = ollama.chat(model=self.model_name, messages=[{"role": "user", "content": prompt}])
            content = response['message']['content'].strip()
            
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            try:
                parsed = json.loads(content)
                status = parsed.get("status", "ambiguous").lower()
                reason = parsed.get("reason", "No reason provided")
                if status in ["distracted", "allowed"]:
                    print(f"--- Warden Decision (Text): {status.upper()} | Reason: {reason} ---")
                    return status, reason
                return "ambiguous", f"Parsed invalid status: {status}"
            except json.JSONDecodeError:
                if "distracted" in content.lower():
                    return "distracted", "Regex fallback: found 'distracted'"
                elif "allowed" in content.lower():
                    return "allowed", "Regex fallback: found 'allowed'"
                return "ambiguous", "Could not parse text semantics"
        except Exception as e:
            print(f"Error in text semantics evaluation: {e}")
            return "ambiguous", f"Model crashed: {str(e)}"

    def evaluate_with_vision(self, goal: str, ocr_text: str, desktop_img: str, webcam_img: str) -> Tuple[str, str]:
        prompt = f"The user is supposed to be focusing on: {goal}. Look at these screenshots. Are they distracted or working? Reply with ONLY a valid JSON object in this format: {{\"status\": \"distracted\" | \"allowed\" | \"focused_but_stuck\", \"reason\": \"a short 1-sentence explanation\"}}"
        
        images = []
        if desktop_img and os.path.exists(desktop_img):
            images.append(desktop_img)
        if webcam_img and os.path.exists(webcam_img):
            images.append(webcam_img)
            
        if not images:
            return "ambiguous", "No images provided to vision model"
            
        try:
            response = self.vision_client.chat(model="gemma4:e4b", messages=[{
                "role": "user", 
                "content": prompt,
                "images": images
            }])
            
            content = response['message']['content'].strip()
            # Try to parse JSON from the response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            try:
                parsed = json.loads(content)
                status = parsed.get("status", "ambiguous").lower()
                reason = parsed.get("reason", "No reason provided")
                if status in ["distracted", "allowed", "focused_but_stuck"]:
                    print(f"--- Warden Decision (Vision): {status.upper()} | Reason: {reason} ---")
                    return status, reason
                else:
                    return "distracted", f"Parsed invalid status: {status}"
            except json.JSONDecodeError:
                if "distracted" in content.lower():
                    return "distracted", "Regex fallback: found 'distracted' in text"
                elif "allowed" in content.lower():
                    return "allowed", "Regex fallback: found 'allowed' in text"
                else:
                    return "distracted", "Could not parse vision response"
                    
        except Exception as e:
            print(f"Error in vision evaluation: {e}")
            return "ambiguous", f"Vision model crashed: {str(e)}"

    def evaluate_desktop_state(self, goal: str, ocr_text: str, desktop_imgs: List[str]) -> Tuple[bool, str]:
        if not desktop_imgs:
            return False, "No desktop screenshots available"
            
        prompt = (
            f"The user's active focus goal is: '{goal}'. "
            f"Here is some OCR text extracted from their screen: '{ocr_text[:500]}...'\n"
            "Evaluate the provided desktop monitor screenshot. "
            "If you see a mix of studying material and distracting activities (like a video game, social media, or movies), the user is distracted. "
            "Do not allow them to bypass the check just because some study text is visible. "
            "Respond with ONLY a valid JSON object in this format:\n"
            "{\"distracted\": true | false, \"reason\": \"a short explanation of what the user is doing or why they are not distracted\"}"
        )
        
        try:
            print(f"--- Warden: Running desktop distraction check on {len(desktop_imgs)} monitors with Gemma Vision ---")
            
            for img_path in desktop_imgs:
                if not os.path.exists(img_path):
                    continue
                    
                response = self.vision_client.chat(model="gemma4:e4b", messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [img_path]
                }])
                
                content = response['message']['content'].strip()
                
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                    
                is_distracted = False
                reason = "No reason provided"
                
                try:
                    parsed = json.loads(content)
                    is_distracted = parsed.get("distracted", False)
                    reason = parsed.get("reason", "No reason provided")
                except json.JSONDecodeError:
                    content_lower = content.lower()
                    if '"distracted": true' in content_lower or '"distracted":true' in content_lower:
                        is_distracted = True
                        reason = "Fallback parsing: desktop distraction detected"
                        
                if is_distracted:
                    print(f"--- Warden Decision (Desktop): DISTRACTED | Reason: {reason} ---")
                    return True, f"Distraction found on a monitor: {reason}"
                    
            print("--- Warden Decision (Desktop): ALLOWED | Reason: All monitors focused ---")
            return False, "All monitors focused"
                
        except Exception as e:
            print(f"Error in desktop state evaluation: {e}")
            return False, f"Vision model failed: {str(e)}"

    def evaluate_physical_state(self, webcam_img: str, goal: str) -> Tuple[bool, str]:
        if not webcam_img or not os.path.exists(webcam_img):
            return False, "No webcam snapshot available"
            
        prompt = (
            f"The user's active focus goal is: '{goal}'. "
            "Analyze the webcam image to see if they are currently physically distracted or not working on their goal. "
            "Specifically check if they are:\n"
            "1. Looking at, holding, or using their mobile phone.\n"
            "2. Looking down or away from their computer screen for non-work-related reasons.\n"
            "3. Sleeping, dozing off, or resting their head on their desk.\n"
            "4. Not present at their desk / not in camera view (empty chair or no person visible).\n\n"
            "CRITICAL: If ANY of the 4 conditions above are met (especially if the person is not at their desk), they are NOT working and you MUST set \"distracted\" to true.\n\n"
            "Respond with ONLY a valid JSON object in this format:\n"
            "{\"distracted\": true | false, \"reason\": \"a short explanation of what the user is doing or why they are not distracted\"}"
        )
        
        try:
            print("--- Warden: Running webcam physical distraction check with Gemma Vision ---")
            response = self.vision_client.chat(model="gemma4:e4b", messages=[{
                "role": "user",
                "content": prompt,
                "images": [webcam_img]
            }])
            
            content = response['message']['content'].strip()
            
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            try:
                parsed = json.loads(content)
                is_distracted = parsed.get("distracted", False)
                reason = parsed.get("reason", "No reason provided")
                print(f"--- Warden Decision (Physical): {'DISTRACTED' if is_distracted else 'ALLOWED'} | Reason: {reason} ---")
                return bool(is_distracted), reason
            except json.JSONDecodeError:
                content_lower = content.lower()
                if '"distracted": true' in content_lower or '"distracted":true' in content_lower:
                    return True, "Fallback parsing: physical distraction detected"
                return False, "Could not parse vision response"
                
        except Exception as e:
            print(f"Error in physical state evaluation: {e}")
            return False, f"Vision model failed: {str(e)}"

    def generate_intervention(self, current_task: str, text: str = None, img_path: str = None, date_added: str = None, target_date: str = None) -> str:
        prompt = f"The user is distracted while working on: {current_task}.\n"
        
        if date_added and target_date:
            prompt += f"This task was added on {date_added} and the target completion date is {target_date}.\n"
            prompt += "If the task is old or overdue, be more authoritative and urge them to clear it off the board.\n"
            
        if text:
            prompt += f"They are looking at this text: {text[:500]}...\n"
        prompt += "Generate exactly one short, punchy, sarcastic sentence to nudge them back to work."
            
        messages = [{"role": "user", "content": prompt + " Do NOT offer to help the user with their task. You cannot directly help the user, you are just there to provide a behavioral intervention or nudge."}]
        
        if img_path and os.path.exists(img_path):
            messages[0]['images'] = [img_path]
            model_to_use = "gemma4:e4b" # Must use a vision model if images are provided
        else:
            model_to_use = self.model_name
            
        try:
            response = ollama.chat(model=model_to_use, messages=messages)
            return response['message']['content'].strip()
        except Exception as e:
            print(f"Error generating intervention: {e}")
            return "Hey, are you still focusing on your task?"

    def generate_praise(self, state_summary: str, minutes_focused: int) -> str:
        prompt = f"The user has been successfully focusing on: '{state_summary}' for {minutes_focused} minutes straight without getting distracted. Generate exactly one short, encouraging, and highly complimentary sentence to praise their focus."
        messages = [{"role": "user", "content": prompt}]
        try:
            response = ollama.chat(model=self.model_name, messages=messages)
            return response['message']['content'].strip()
        except Exception as e:
            print(f"Error generating praise: {e}")
            return f"Great job focusing for the last {minutes_focused} minutes!"

    async def speak_text(self, text: str):
        if not hasattr(self, 'tts_lock'):
            self.tts_lock = asyncio.Lock()
            
        async with self.tts_lock:
            print(f"--- TTS Speaking: {text} ---")
            try:
                response = await self.tts_client.audio.speech.create(
                    model="tts-1",
                    voice="vivian",
                    response_format="wav",
                    input=text
                )
                output_file = "temp_nudge.wav"
                
                def _play_audio():
                    try:
                        # OpenAI async client response handling
                        response.stream_to_file(output_file)
                        pygame.mixer.music.load(output_file)
                        pygame.mixer.music.play()
                        import time
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.1)
                    except Exception as e:
                        print(f"Pygame failed to play audio: {e}")
                    
                await asyncio.to_thread(_play_audio)
            except Exception as e:
                print(f"Error in TTS: {e}")
