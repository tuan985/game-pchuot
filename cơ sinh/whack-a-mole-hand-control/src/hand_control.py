import time
import math
import cv2
import mediapipe as mp


class HandController:
    """
    Quản lý camera + MediaPipe hands.

    Methods:
      - start_detection(src=0, width=640, height=480): mở camera
      - stop_detection(): giải phóng camera
      - get_hand_position(): trả về (hand_pos, gesture, frame)
         hand_pos: (x,y) pixel của WRIST hoặc None
         gesture: True khi phát hiện nắm tay (fist) theo vị trí hoặc góc, có cooldown
         frame: frame BGR (đã flip) có vẽ landmarks (dùng để hiển thị)
      - last_angles: dict lưu góc từng ngón (deg)
      - last_clench_speed: tốc độ thay đổi mean-angle (deg/s)
    """

    def __init__(self, max_hands=1, min_detection_confidence=0.6, min_tracking_confidence=0.5):
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

        self.cap = None
        self.last_angles = {}            # {'thumb','index','middle','ring','pinky'} in degrees
        self.prev_mean_angle = None      # previous frame mean of finger angles
        self.prev_mean_time = None
        self.last_clench_speed = 0.0     # deg / s
        self.gesture_cooldown = 0.3      # seconds between gestures
        self.last_gesture_time = 0.0

    def start_detection(self, src=0, width=640, height=480):
        """Open camera (index or path). Safe to call multiple times."""
        if self.cap is not None and self.cap.isOpened():
            return
        self.cap = cv2.VideoCapture(src)
        try:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        except Exception:
            pass

    def stop_detection(self):
        """Release camera and close OpenCV windows."""
        try:
            if self.cap is not None:
                self.cap.release()
                self.cap = None
        finally:
            cv2.destroyAllWindows()

    def _angle_between_vectors(self, v1, v2):
        """Return angle in degrees between 2D vectors v1 and v2."""
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        mag1 = math.hypot(v1[0], v1[1])
        mag2 = math.hypot(v2[0], v2[1])
        if mag1 == 0 or mag2 == 0:
            return 0.0
        cosang = max(-1.0, min(1.0, dot / (mag1 * mag2)))
        return math.degrees(math.acos(cosang))

    def compute_finger_angles(self, hand_landmarks, image=None, draw=True):
        """
        Compute angles (degrees) for each finger and update last_angles.
        - thumb: angle at THUMB_IP between vectors (THUMB_MCP->THUMB_IP) and (THUMB_TIP->THUMB_IP)
        - index/middle/ring/pinky: angle at PIP between vectors (MCP->PIP) and (DIP->PIP)
        Also compute mean of index..pinky and update last_clench_speed (deg/s).
        If image provided and draw=True, angle texts are drawn on image.
        """
        lm = hand_landmarks.landmark
        h, w = (None, None)
        if image is not None:
            h, w = image.shape[:2]

        def to_px(pt):
            return (int(pt.x * w), int(pt.y * h)) if (w and h) else (pt.x, pt.y)

        angles = {}

        # Thumb: use MCP, IP, TIP -> angle at IP
        try:
            thumb_mcp = to_px(lm[self.mp_hands.HandLandmark.THUMB_MCP])
            thumb_ip = to_px(lm[self.mp_hands.HandLandmark.THUMB_IP])
            thumb_tip = to_px(lm[self.mp_hands.HandLandmark.THUMB_TIP])
            v1 = (thumb_mcp[0] - thumb_ip[0], thumb_mcp[1] - thumb_ip[1])
            v2 = (thumb_tip[0] - thumb_ip[0], thumb_tip[1] - thumb_ip[1])
            angles['thumb'] = self._angle_between_vectors(v1, v2)
            if draw and image is not None:
                cv2.putText(image, f"{int(angles['thumb'])}", (thumb_ip[0] - 12, thumb_ip[1] - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        except Exception:
            angles['thumb'] = 0.0

        # Other fingers: angle at PIP using MCP, PIP, DIP
        finger_defs = [
            ('index', self.mp_hands.HandLandmark.INDEX_FINGER_MCP, self.mp_hands.HandLandmark.INDEX_FINGER_PIP, self.mp_hands.HandLandmark.INDEX_FINGER_DIP),
            ('middle', self.mp_hands.HandLandmark.MIDDLE_FINGER_MCP, self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP, self.mp_hands.HandLandmark.MIDDLE_FINGER_DIP),
            ('ring', self.mp_hands.HandLandmark.RING_FINGER_MCP, self.mp_hands.HandLandmark.RING_FINGER_PIP, self.mp_hands.HandLandmark.RING_FINGER_DIP),
            ('pinky', self.mp_hands.HandLandmark.PINKY_MCP, self.mp_hands.HandLandmark.PINKY_PIP, self.mp_hands.HandLandmark.PINKY_DIP),
        ]

        for name, mcp_i, pip_i, dip_i in finger_defs:
            try:
                mcp = to_px(lm[mcp_i])
                pip = to_px(lm[pip_i])
                dip = to_px(lm[dip_i])
                v1 = (mcp[0] - pip[0], mcp[1] - pip[1])
                v2 = (dip[0] - pip[0], dip[1] - pip[1])
                ang = self._angle_between_vectors(v1, v2)
                angles[name] = ang
                if draw and image is not None:
                    cv2.putText(image, f"{int(ang)}", (pip[0] - 12, pip[1] - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            except Exception:
                angles[name] = 0.0

        # update last_angles
        self.last_angles = angles

        # compute clench speed: change of mean(index..pinky) / dt
        now = time.time()
        mean_f = 0.0
        cnt = 0
        for k in ('index', 'middle', 'ring', 'pinky'):
            mean_f += angles.get(k, 0.0)
            cnt += 1
        mean_f = (mean_f / cnt) if cnt else 0.0

        if self.prev_mean_angle is not None and self.prev_mean_time is not None:
            dt = now - self.prev_mean_time
            if dt > 0:
                speed = (mean_f - self.prev_mean_angle) / dt
            else:
                speed = 0.0
        else:
            speed = 0.0

        self.last_clench_speed = speed
        self.prev_mean_angle = mean_f
        self.prev_mean_time = now

        return angles

    def get_hand_position(self):
        """
        Read camera frame, detect hand, compute wrist position, angles and gesture.
        Returns (hand_pos, gesture, frame).
        """
        if self.cap is None:
            return None, False, None

        success, frame = self.cap.read()
        if not success or frame is None:
            return None, False, None

        frame = cv2.flip(frame, 1)  # mirror
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)

        hand_pos = None
        gesture = False

        if results.multi_hand_landmarks:
            # use first detected hand
            hand_landmarks = results.multi_hand_landmarks[0]
            self.mp_draw.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)

            # wrist position in pixels
            try:
                wpt = hand_landmarks.landmark[self.mp_hands.HandLandmark.WRIST]
                hand_pos = (int(wpt.x * frame.shape[1]), int(wpt.y * frame.shape[0]))
            except Exception:
                hand_pos = None

            # angles (and draw)
            self.compute_finger_angles(hand_landmarks, image=frame, draw=True)

            # detect fist by comparing tip.y and pip.y for 4 fingers
            folded = 0
            try:
                tips = [self.mp_hands.HandLandmark.INDEX_FINGER_TIP,
                        self.mp_hands.HandLandmark.MIDDLE_FINGER_TIP,
                        self.mp_hands.HandLandmark.RING_FINGER_TIP,
                        self.mp_hands.HandLandmark.PINKY_TIP]
                pips = [self.mp_hands.HandLandmark.INDEX_FINGER_PIP,
                        self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP,
                        self.mp_hands.HandLandmark.RING_FINGER_PIP,
                        self.mp_hands.HandLandmark.PINKY_PIP]
                for tip, pip in zip(tips, pips):
                    if hand_landmarks.landmark[tip].y > hand_landmarks.landmark[pip].y:
                        folded += 1
            except Exception:
                folded = 0

            # optionally also use angle threshold
            ang_fold_count = sum(1 for k in ('index', 'middle', 'ring', 'pinky') if self.last_angles.get(k, 0.0) > 60)

            now = time.time()
            folded_ok = (folded >= 3) or (ang_fold_count >= 3)
            if folded_ok and (now - self.last_gesture_time) > self.gesture_cooldown:
                gesture = True
                self.last_gesture_time = now

        return hand_pos, gesture, frame
