import json
from pydantic import BaseModel
from typing import List, Tuple, Optional
import ollama
from openai import OpenAI
import pygame
import asyncio
import os

class GoalParseResult(BaseModel):
    goal_summary: str
    allowed_applications: List[str]
    allowed_keywords: List[str]

class Warden:
    def __init__(self, tts_url: str):
        self.tts_url = tts_url
        self.model_name = "gemma4:e4b" # Change to specific model name as needed
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"Pygame mixer init failed: {e}")

    def parse_user_goal(self, user_prompt: str) -> GoalParseResult:
        system_prompt = "You are an AI assistant helping a user focus. Extract the main goal, and infer allowed software and keywords based on their prompt. Return valid JSON only, following this schema: {'goal_summary': 'string', 'allowed_applications': ['string'], 'allowed_keywords': ['string']}"
        
        try:
            print(f"--- Warden: Sending chat request to Ollama using model {self.model_name} ---")
            response = ollama.chat(model=self.model_name, messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"My goal for this session is: {user_prompt}"}
            ], format="json")
            
            print(f"--- Warden: Received response from Ollama ---")
            data = json.loads(response['message']['content'])
            print(f"--- Warden: JSON parsed successfully: {data} ---")
            return GoalParseResult(**data)
        except Exception as e:
            print(f"--- Warden: Failed to parse goal: {e} ---")
            import traceback
            traceback.print_exc()
            return GoalParseResult(goal_summary=user_prompt, allowed_applications=[], allowed_keywords=[])

    def check_keywords(self, text: str, allowed_keywords: List[str], allowed_apps: List[str], app_name: str) -> Tuple[str, str]:
        text_lower = text.lower()
        app_lower = app_name.lower()
        
        # Check if the app itself is allowed
        for app in allowed_apps:
            if app.lower() in app_lower:
                return "allowed", f"App matched allowed list: '{app}'"
                
        # Check if any allowed keywords are present in the OCR text or window title
        for kw in allowed_keywords:
            if kw.lower() in text_lower or kw.lower() in app_lower:
                return "allowed", f"Keyword matched: '{kw}'"
                
        # Known distraction keywords (could be moved to config)
        distraction_keywords = ["netflix", "twitter", "facebook", "instagram", "tiktok"]
        for kw in distraction_keywords:
            if kw in app_lower or kw in text_lower:
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

    def evaluate_with_vision(self, goal: str, ocr_text: str, desktop_img: str, webcam_img: str, emotion: str = "neutral") -> Tuple[str, str]:
        prompt = f"The user is supposed to be focusing on: {goal}. Their current facial expression was evaluated as: '{emotion}'. Look at these screenshots. Are they distracted or working? Reply with ONLY a valid JSON object in this format: {{\"status\": \"distracted\" | \"allowed\" | \"focused_but_stuck\", \"reason\": \"a short 1-sentence explanation\"}}"
        
        images = []
        if desktop_img and os.path.exists(desktop_img):
            images.append(desktop_img)
        if webcam_img and os.path.exists(webcam_img):
            images.append(webcam_img)
            
        if not images:
            return "ambiguous", "No images provided to vision model"
            
        try:
            client = ollama.Client(timeout=60.0)
            response = client.chat(model="gemma4:e4b", messages=[{
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
            client = ollama.Client(timeout=60.0)
            
            for img_path in desktop_imgs:
                if not os.path.exists(img_path):
                    continue
                    
                response = client.chat(model="gemma4:e4b", messages=[{
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
                    return True, f"Distraction found on a monitor: {reason}"
                    
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
            "Respond with ONLY a valid JSON object in this format:\n"
            "{\"distracted\": true | false, \"reason\": \"a short explanation of what the user is doing or why they are not distracted\"}"
        )
        
        try:
            print("--- Warden: Running webcam physical distraction check with Gemma Vision ---")
            client = ollama.Client(timeout=60.0)
            response = client.chat(model="gemma4:e4b", messages=[{
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
                return bool(is_distracted), reason
            except json.JSONDecodeError:
                content_lower = content.lower()
                if '"distracted": true' in content_lower or '"distracted":true' in content_lower:
                    return True, "Fallback parsing: physical distraction detected"
                return False, "Could not parse vision response"
                
        except Exception as e:
            print(f"Error in physical state evaluation: {e}")
            return False, f"Vision model failed: {str(e)}"

    def evaluate_emotion(self, image_paths: str | list) -> str:
        try:
            from deepface import DeepFace
            from statistics import mode
            
            if isinstance(image_paths, str):
                image_paths = [image_paths]
                
            emotions = []
            for path in image_paths:
                if not os.path.exists(path):
                    continue
                try:
                    res = DeepFace.analyze(path, actions=['emotion'], enforce_detection=False)
                    if isinstance(res, list):
                        res = res[0]
                    emotions.append(res.get('dominant_emotion', 'neutral'))
                except Exception:
                    pass
                    
            if not emotions:
                return "neutral"
                
            return mode(emotions)
        except Exception as e:
            print(f"Error evaluating emotion: {e}")
            return "neutral"

    def generate_intervention(self, state_summary: str, ocr_text: str, image_path: Optional[str], emotion: str = "neutral") -> str:
        if emotion in ["sad", "angry", "fear"]:
            prompt = f"The user's goal is: '{state_summary}'. They are currently distracted. They are looking at: '{ocr_text[:200]}...'. Their face shows they are feeling {emotion}/frustrated. Generate exactly one short, slightly sarcastic sentence to nudge them back to work. Do NOT suggest they take a break or stop working."
        else:
            emotion_str = f" Their face shows they are feeling {emotion}." if emotion != "neutral" else ""
            prompt = f"The user's goal is: '{state_summary}'. They are currently distracted. They are looking at: '{ocr_text[:200]}...'.{emotion_str} Generate exactly one short, punchy, sarcastic sentence to nudge them back to work."
            
        messages = [{"role": "user", "content": prompt + " Do NOT offer to help the user with their task. You cannot directly help the user, you are just there to provide a behavioral intervention or nudge."}]
        
        if image_path and os.path.exists(image_path):
            messages[0]['images'] = [image_path]
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
        try:
            from openai import AsyncOpenAI
            # Assumes base URL includes /v1 if needed, or parse it appropriately
            base_url = self.tts_url
            if base_url.endswith("/v1/audio/speech"):
                base_url = base_url.replace("/audio/speech", "")
            
            client = AsyncOpenAI(base_url=base_url, api_key="not-needed")
            response = await client.audio.speech.create(
                model="tts-1",
                voice="sohee",
                response_format="wav",
                input=text
            )
            output_file = "temp_nudge.wav"
            
            # Streaming to file is synchronous in httpx, use a thread or just write bytes
            with open(output_file, 'wb') as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
            
            pygame.mixer.music.load(output_file)
            pygame.mixer.music.play()
        except Exception as e:
            print(f"Error in TTS: {e}")
