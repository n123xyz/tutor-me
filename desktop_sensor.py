import pytesseract
from PIL import Image
import subprocess
import os

class DesktopSensor:
    def __init__(self):
        pass

    def _capture_screen(self, filepath: str, quality: str = "80"):
        # Use pyscreenshot which intelligently falls back across Wayland/X11 backends
        # to prevent solid black screenshots.
        try:
            import pyscreenshot as ImageGrab
            print(f"--- DesktopSensor: Capturing screenshot using pyscreenshot to {filepath} ---")
            im = ImageGrab.grab()
            
            # Pyscreenshot sometimes captures RGBA. Convert to RGB to save as JPEG.
            if im.mode in ('RGBA', 'P'):
                im = im.convert('RGB')
                
            im.save(filepath, format="JPEG", quality=int(quality))
            print("--- DesktopSensor: Pyscreenshot capture successful ---")
            return True
        except Exception as e:
            print(f"Pyscreenshot failed: {e}")
            return False

    def get_screen_text(self) -> str:
        try:
            temp_file = "temp_ocr_screenshot.jpg"
            if self._capture_screen(temp_file):
                image = Image.open(temp_file)
                text = pytesseract.image_to_string(image)
                
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    
                return text
            return ""
        except Exception as e:
            print(f"Error in OCR text extraction: {e}")
            return ""

    def get_screenshot_path(self) -> str:
        try:
            path = "temp_screenshot.jpg"
            if self._capture_screen(path, "70"):
                # Downscale aggressively to save vision model processing time
                image = Image.open(path)
                image.thumbnail((800, 600))
                image.save(path, format="JPEG", quality=70)
                return path
            return ""
        except Exception as e:
            print(f"Error capturing screenshot to file: {e}")
            return ""

    def get_screen_text_and_image(self) -> tuple[str, str]:
        try:
            path = "temp_screenshot.jpg"
            if self._capture_screen(path, "80"):
                image = Image.open(path)
                # Perform OCR on full resolution image
                text = pytesseract.image_to_string(image)
                
                # Downscale for the vision model
                image.thumbnail((800, 600))
                image.save(path, format="JPEG", quality=70)
                return text, path
            return "", ""
        except Exception as e:
            print(f"Error in OCR and image capture: {e}")
            return "", ""
