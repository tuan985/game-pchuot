import time
import cv2
import mediapipe as mp

class HandController:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands()
        self.mp_draw = mp.solutions.drawing_utils
        self.prev_y = None
        self.prev_time = None
        self.gesture_cooldown = 0.3  # giây
        self.last_gesture_time = 0

    def start_detection(self):
        self.cap = cv2.VideoCapture(0)

    def get_hand_position(self):
        success, image = self.cap.read()
        if not success:
            return None, False, None

        image = cv2.flip(image, 1)
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self.hands.process(image_rgb)

        hand_pos = None
        gesture = False

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(image, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                if len(hand_landmarks.landmark) > self.mp_hands.HandLandmark.WRIST:
                    wrist = hand_landmarks.landmark[self.mp_hands.HandLandmark.WRIST]
                    x = int(wrist.x * image.shape[1])
                    y = int(wrist.y * image.shape[0])
                    hand_pos = (x, y)
                else:
                    hand_pos = None

                # Kiểm tra nắm tay (fist)
                fingers_folded = 0
                finger_tips = [
                    self.mp_hands.HandLandmark.INDEX_FINGER_TIP,
                    self.mp_hands.HandLandmark.MIDDLE_FINGER_TIP,
                    self.mp_hands.HandLandmark.RING_FINGER_TIP,
                    self.mp_hands.HandLandmark.PINKY_TIP
                ]
                finger_pips = [
                    self.mp_hands.HandLandmark.INDEX_FINGER_PIP,
                    self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP,
                    self.mp_hands.HandLandmark.RING_FINGER_PIP,
                    self.mp_hands.HandLandmark.PINKY_PIP
                ]
                for tip, pip in zip(finger_tips, finger_pips):
                    if hand_landmarks.landmark[tip].y > hand_landmarks.landmark[pip].y:
                        fingers_folded += 1
                # Nếu 3 hoặc 4 ngón gập lại thì coi là nắm tay
                if fingers_folded >= 3:
                    gesture = True
                break

        return hand_pos, gesture, image

    def stop_detection(self):
        self.cap.release()
        cv2.destroyAllWindows()