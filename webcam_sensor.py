import cv2
import os

class WebcamSensor:
    def __init__(self, camera_index=0):
        self.camera_index = camera_index

    def get_snapshot_path(self) -> str:
        try:
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                print("Could not open webcam.")
                return ""
            
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                path = "temp_webcam.jpg"
                cv2.imwrite(path, frame)
                return path
            else:
                return ""
        except Exception as e:
            print(f"Error capturing webcam snapshot: {e}")
            return ""
