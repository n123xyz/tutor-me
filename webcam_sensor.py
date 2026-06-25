import cv2
import os
import time

class WebcamSensor:
    def __init__(self, camera_index=0):
        self.camera_index = camera_index

    def get_snapshot_path(self) -> str:
        """Kept for backwards compatibility."""
        paths = self.get_video_snapshots(duration=0.5, num_frames=1)
        return paths[0] if paths else ""

    def get_video_snapshots(self, duration=15.0, num_frames=15) -> list[str]:
        """
        Captures `num_frames` snapshots evenly spaced over `duration` seconds.
        Warms up the camera by discarding the first few frames.
        Returns a list of file paths to the captured frames.
        """
        try:
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                print("Could not open webcam.")
                return []
            
            # Warm up the camera for auto-exposure/auto-focus
            for _ in range(10):
                cap.read()
                
            paths = []
            interval = duration / num_frames if num_frames > 1 else 0
            
            for i in range(num_frames):
                start_t = time.time()
                ret, frame = cap.read()
                if ret:
                    path = f"temp_webcam_{i}.jpg"
                    cv2.imwrite(path, frame)
                    paths.append(path)
                
                # Sleep to space out the frames
                elapsed = time.time() - start_t
                sleep_time = max(0, interval - elapsed)
                if sleep_time > 0 and i < num_frames - 1:
                    time.sleep(sleep_time)
            
            cap.release()
            return paths
            
        except Exception as e:
            print(f"Error capturing webcam snapshots: {e}")
            if 'cap' in locals():
                cap.release()
            return []
