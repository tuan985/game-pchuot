# ==========================================================
# FILE: hand_control.py
# PHIÊN BẢN: Cải tiến độ chính xác (Đo độ cong ngón tay)
# ==========================================================

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe.framework.formats import landmark_pb2
import numpy as np
import time
import os

# ==========================================================
# LỚP BỘ LỌC KALMAN ĐƠN GIẢN
# ==========================================================
class KalmanFilter:
    """
    Một bộ lọc Kalman tuyến tính đơn giản cho 1 điểm 3D.
    Trạng thái (state) bao gồm [x, y, z, vx, vy, vz].
    """
    def __init__(self, dt=1./60, process_noise=5e-5, measurement_noise=5e-3):
        self.dt = dt
        # State: [x, y, z, vx, vy, vz]
        self.x = np.zeros((6, 1))
        # State transition matrix (A) for constant velocity model
        self.A = np.array([
            [1, 0, 0, dt, 0, 0],
            [0, 1, 0, 0, dt, 0],
            [0, 0, 1, 0, 0, dt],
            [0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 1]
        ], dtype=np.float32)
        # Measurement matrix (H) - we only measure position
        self.H = np.array([
            [1, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0]
        ], dtype=np.float32)
        # Process noise covariance (Q)
        self.Q = np.eye(6, dtype=np.float32) * process_noise
        # Measurement noise covariance (R)
        self.R = np.eye(3, dtype=np.float32) * measurement_noise
        # State estimate covariance (P)
        self.P = np.eye(6, dtype=np.float32)

    def predict(self):
        """Dự đoán trạng thái tiếp theo."""
        self.x = self.A @ self.x
        self.P = self.A @ self.P @ self.A.T + self.Q
        return self.x

    def update(self, z):
        """Cập nhật trạng thái với một phép đo mới."""
        y = z - self.H @ self.x # Innovation
        S = self.H @ self.P @ self.H.T + self.R # Innovation covariance
        try:
            K = self.P @ self.H.T @ np.linalg.inv(S) # Kalman Gain
            self.x = self.x + K @ y
            self.P = (np.eye(6) - K @ self.H) @ self.P
        except np.linalg.LinAlgError:
            # Bỏ qua lỗi nếu ma trận không thể đảo ngược
            pass

    def reset(self, initial_pos):
        """Reset bộ lọc với vị trí mới."""
        self.x = np.zeros((6, 1))
        self.x[:3] = initial_pos.reshape(3, 1)
        self.P = np.eye(6, dtype=np.float32)

# ==========================================================
# LỚP HANDCONTROLLER CHÍNH
# ==========================================================
class HandController:
    """
    Xử lý việc phát hiện tay, lọc Kalman và tính toán cơ sinh học.
    """
    def __init__(self, max_hands=1, min_detection_confidence=0.5, min_tracking_confidence=0.5):
        
        # Tìm file model 'hand_landmarker.task' trong cùng thư mục với file .py này
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.model_path = os.path.join(base_dir, 'hand_landmarker.task')
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Không tìm thấy file 'hand_landmarker.task' tại: {self.model_path}. Hãy đảm bảo bạn đã tải file model và đặt nó vào cùng thư mục với 'hand_control.py'.")

        # Cài đặt MediaPipe
        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_tracking_confidence,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(options)
        self.mp_draw = mp.solutions.drawing_utils
        self.mp_hands = mp.solutions.hands

        self.cap = None
        self.frame_timestamp_ms = 0

        # Biến lưu trữ dữ liệu hiệu chỉnh
        self.static_profile = {} # Lưu tỷ lệ xương
        self.angle_extended_dict = {} # Lưu góc duỗi tối đa
        self.is_calibrated = False

        # Cài đặt Kalman
        self.GAME_FPS = 60 
        self.KALMAN_DT = 1.0 / self.GAME_FPS
        self.kalman_filters = [KalmanFilter(dt=self.KALMAN_DT, process_noise=5e-5, measurement_noise=5e-3) for _ in range(21)]
        self.is_kalman_initialized = False
        self.frames_without_hand = 0
        self.RESET_THRESHOLD = 15 # Số frame không thấy tay trước khi reset Kalman

        # Hằng số cơ sinh học
        self.BONE_CONSTRAINT_TOLERANCE = 0.35 # Độ co giãn cho phép của xương
        self.OUTLIER_THRESHOLD = 0.55 # Ngưỡng nhận diện tín hiệu nhiễu

        self.FINGERS_LIST = ["thumb", "index", "middle", "ring", "pinky"]
        # Xương tham chiếu (khoảng cách giữa 2 khớp này) để tính tỷ lệ
        self.REFERENCE_BONES = (self.mp_hands.HandLandmark.INDEX_FINGER_MCP, self.mp_hands.HandLandmark.PINKY_MCP)
        
        # ==========================================================
        # (SỬA) THAY ĐỔI QUAN TRỌNG: ĐỊNH NGHĨA LẠI CÁCH ĐO GÓC GẬP (CURL)
        # ==========================================================
        # Cách mới (đo độ cong của ngón, chính xác hơn):
        self.ANGLES_TO_MEASURE_DEF = {
            'index': (self.mp_hands.HandLandmark.INDEX_FINGER_MCP, self.mp_hands.HandLandmark.INDEX_FINGER_PIP, self.mp_hands.HandLandmark.INDEX_FINGER_TIP),
            'middle': (self.mp_hands.HandLandmark.MIDDLE_FINGER_MCP, self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP, self.mp_hands.HandLandmark.MIDDLE_FINGER_TIP),
            'ring': (self.mp_hands.HandLandmark.RING_FINGER_MCP, self.mp_hands.HandLandmark.RING_FINGER_PIP, self.mp_hands.HandLandmark.RING_FINGER_TIP),
            'pinky': (self.mp_hands.HandLandmark.PINKY_MCP, self.mp_hands.HandLandmark.PINKY_PIP, self.mp_hands.HandLandmark.PINKY_TIP),
            'thumb': (self.mp_hands.HandLandmark.THUMB_MCP, self.mp_hands.HandLandmark.THUMB_IP, self.mp_hands.HandLandmark.THUMB_TIP),
        }
        # ==========================================================
        
        # Các xương dùng để đo độ dài và tỷ lệ (để lưu file Excel)
        self.BONE_INDICES_TO_MONITOR = {
            'index_mcp': (self.mp_hands.HandLandmark.INDEX_FINGER_MCP, self.mp_hands.HandLandmark.INDEX_FINGER_PIP),
            'index_pip': (self.mp_hands.HandLandmark.INDEX_FINGER_PIP, self.mp_hands.HandLandmark.INDEX_FINGER_DIP),
            'middle_mcp': (self.mp_hands.HandLandmark.MIDDLE_FINGER_MCP, self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP),
            'middle_pip': (self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP, self.mp_hands.HandLandmark.MIDDLE_FINGER_DIP),
            'ring_mcp': (self.mp_hands.HandLandmark.RING_FINGER_MCP, self.mp_hands.HandLandmark.RING_FINGER_PIP),
            'pinky_mcp': (self.mp_hands.HandLandmark.PINKY_MCP, self.mp_hands.HandLandmark.PINKY_PIP),
        }
        # Đây là danh sách quan trọng dùng để khớp với file app.py
        self.BONE_NAMES_LIST = list(self.BONE_INDICES_TO_MONITOR.keys())

    def start_detection(self, src=0, width=640, height=480):
        """Khởi động camera."""
        if self.cap is not None and self.cap.isOpened(): return True
        self.cap = cv2.VideoCapture(src)
        if not self.cap.isOpened():
            print(f"Lỗi: không thể mở camera tại nguồn {src}"); self.cap = None; return False
        try:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            print(f"Camera đã mở (nguồn {src})"); return True
        except Exception as e:
            print(f"Lỗi khi cài đặt camera: {e}"); return False

    def stop_detection(self):
        """Giải phóng camera và đóng cửa sổ."""
        try:
            if self.cap is not None:
                self.cap.release(); self.cap = None; print("Camera đã đóng")
        finally:
            cv2.destroyAllWindows(); self.landmarker.close()

    # --- Các hàm hỗ trợ tính toán ---
    def _hpr_distance(self, p1, p2): 
        """Tính khoảng cách Euclide giữa 2 điểm 3D."""
        return np.linalg.norm(p1 - p2)
        
    def _hpr_angle(self, p1, p2, p3):
        """Tính góc (p1-p2-p3) tại đỉnh p2."""
        v1 = p1 - p2; v2 = p3 - p2
        dot = np.dot(v1, v2); norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm < 1e-9: return 180.0 # Tránh lỗi chia cho 0
        # TRẢ VỀ ĐƠN VỊ LÀ ĐỘ (DEGREES)
        return np.degrees(np.arccos(np.clip(dot / norm, -1.0, 1.0)))
        
    def _hpr_landmarks_to_array(self, landmark_list):
        """Chuyển danh sách landmark của MediaPipe sang mảng NumPy (21, 3)."""
        return np.array([[lm.x, lm.y, lm.z] for lm in landmark_list])

    def _get_biomechanics(self, landmarks):
        """
        Tính toán các thông số cơ sinh học (độ dài, tỷ lệ) và phát hiện nhiễu.
        Trả về: (bool_is_outlier, dict_lengths, dict_ratios)
        """
        current_lengths = {name: 0.0 for name in self.BONE_NAMES_LIST}
        current_ratios = {name: 0.0 for name in self.BONE_NAMES_LIST}
        is_outlier = False
        
        try:
            # Lấy xương tham chiếu
            p_ref_1 = landmarks[self.REFERENCE_BONES[0]]
            p_ref_2 = landmarks[self.REFERENCE_BONES[1]]
            L_ref_current = self._hpr_distance(p_ref_1, p_ref_2)
            
            if L_ref_current < 1e-6: # Nếu thước đo quá nhỏ, coi như nhiễu
                return True, current_lengths, current_ratios 

            # Tính độ dài và tỷ lệ cho các xương cần theo dõi
            for name, (p1_idx, p2_idx) in self.BONE_INDICES_TO_MONITOR.items():
                length = self._hpr_distance(landmarks[p1_idx], landmarks[p2_idx])
                ratio = length / L_ref_current
                
                current_lengths[name] = length
                current_ratios[name] = ratio

                # Nếu đã hiệu chỉnh, so sánh tỷ lệ hiện tại với tỷ lệ tĩnh
                if self.is_calibrated:
                    static_ratio = self.static_profile.get(name, ratio)
                    if static_ratio > 1e-6:
                        deviation = abs(ratio - static_ratio) / static_ratio
                        # Nếu độ lệch vượt ngưỡng, đánh dấu là nhiễu (outlier)
                        if deviation > self.OUTLIER_THRESHOLD:
                            is_outlier = True
                    else:
                        is_outlier = True
            
            return is_outlier, current_lengths, current_ratios
        
        except Exception:
            # Nếu có bất kỳ lỗi nào (ví dụ: landmark không tồn tại), trả về là nhiễu
            return True, current_lengths, current_ratios

    def apply_bone_constraints(self, landmarks_array):
        """
        Điều chỉnh các khớp đã lọc Kalman để tuân thủ tỷ lệ xương đã hiệu chỉnh.
        Giúp bàn tay không bị "biến dạng" do lỗi lọc.
        """
        try:
            p_ref_1 = landmarks_array[self.REFERENCE_BONES[0]]
            p_ref_2 = landmarks_array[self.REFERENCE_BONES[1]]
            L_ref_current = self._hpr_distance(p_ref_1, p_ref_2)
            if L_ref_current < 1e-6: return landmarks_array

            for name, static_ratio in self.static_profile.items():
                if name not in self.BONE_INDICES_TO_MONITOR: continue
                
                p1_idx, p2_idx = self.BONE_INDICES_TO_MONITOR[name]
                p1 = landmarks_array[p1_idx]; p2 = landmarks_array[p2_idx]
                vec = p2 - p1; curr_len = np.linalg.norm(vec)
                if curr_len < 1e-9: continue

                # Tính độ dài mong muốn dựa trên tỷ lệ đã hiệu chỉnh
                desired_len = static_ratio * L_ref_current
                tolerance = desired_len * self.BONE_CONSTRAINT_TOLERANCE
                lower, upper = desired_len - tolerance, desired_len + tolerance

                # Nếu độ dài hiện tại nằm ngoài ngưỡng cho phép, kẹp nó lại
                if curr_len < lower or curr_len > upper:
                    new_len = np.clip(curr_len, lower, upper)
                    # Di chuyển điểm p2 để đạt được độ dài new_len
                    landmarks_array[p2_idx] = p1 + (vec / curr_len) * new_len
            return landmarks_array
        except Exception:
            return landmarks_array

    def calibrate(self, hand_landmarks_list):
        """
        Thực hiện hiệu chỉnh: lưu lại tỷ lệ xương và góc duỗi tối đa.
        """
        print("Đang hiệu chỉnh..."); 
        landmarks = self._hpr_landmarks_to_array(hand_landmarks_list)
        try:
            # Lấy tỷ lệ xương từ hàm _get_biomechanics
            # self.static_profile sẽ được gán giá trị tại đây
            _, _, self.static_profile = self._get_biomechanics(landmarks) 

            # Lấy góc duỗi tối đa (theo định nghĩa MỚI)
            self.angle_extended_dict = {name: self._hpr_angle(landmarks[p1], landmarks[p2], landmarks[p3])
                                        for name, (p1, p2, p3) in self.ANGLES_TO_MEASURE_DEF.items()}
            
            # Kiểm tra xem dữ liệu hiệu chỉnh có hợp lệ không
            if not self.static_profile or not self.angle_extended_dict:
                print("Lỗi hiệu chỉnh: Không thể tính toán hồ sơ tĩnh."); return False

            self.is_calibrated = True; 
            print("...Hiệu chỉnh thành công!"); 
            return True
            
        except Exception as e:
            print(f"Lỗi hiệu chỉnh: {e}"); 
            self.is_calibrated = False; 
            return False

    def get_frame_data(self):
        """
        Hàm chính: Lấy frame từ camera, xử lý và trả về dữ liệu.
        """
        if self.cap is None or not self.cap.isOpened():
            # Trả về dữ liệu rỗng nếu camera không bật
            return None, self._get_default_rehab_data(), None

        success, frame = self.cap.read()
        if not success or frame is None:
            return None, self._get_default_rehab_data(), None

        frame = cv2.flip(frame, 1) # Lật frame
        self.frame_timestamp_ms = int(time.time() * 1000) 
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        
        # Bước 1: Dự đoán (Predict) vị trí tiếp theo bằng Kalman
        if self.is_kalman_initialized:
            predicted_landmarks = np.array([kf.predict()[:3].flatten() for kf in self.kalman_filters])
        else:
            predicted_landmarks = np.zeros((21, 3)) # Mảng rỗng nếu chưa khởi tạo

        # Bước 2: Phát hiện (Detect) vị trí thực tế bằng MediaPipe
        results = self.landmarker.detect_for_video(mp_image, self.frame_timestamp_ms)
        
        hand_landmarks_list = None
        rehab_data = self._get_default_rehab_data()
        final_landmarks = predicted_landmarks # Mặc định dùng vị trí dự đoán

        if results.hand_landmarks:
            # Nếu thấy tay
            self.frames_without_hand = 0
            hand_landmarks_list = results.hand_landmarks[0]
            measured_landmarks = self._hpr_landmarks_to_array(hand_landmarks_list)

            if not self.is_kalman_initialized:
                # Lần đầu tiên thấy tay, reset bộ lọc Kalman về vị trí này
                for i, lm in enumerate(measured_landmarks):
                    self.kalman_filters[i].reset(lm)
                self.is_kalman_initialized = True
                final_landmarks = measured_landmarks # Dùng ngay vị trí đo được
            
            # Tính toán thông số cơ sinh học từ dữ liệu đo được
            is_outlier, lengths, ratios = self._get_biomechanics(measured_landmarks)
            
            # Gán dữ liệu này vào kết quả trả về
            # Đây là mấu chốt để lưu file Excel
            rehab_data['is_outlier'] = is_outlier
            rehab_data['bone_lengths'] = lengths
            rehab_data['bone_ratios'] = ratios

            if not is_outlier:
                # Nếu tín hiệu tốt (không nhiễu), cập nhật (Update) bộ lọc Kalman
                for i, lm in enumerate(measured_landmarks):
                    self.kalman_filters[i].update(lm.reshape(3, 1))
            
            # Lấy vị trí đã được làm mượt (vị trí đã update)
            final_landmarks = np.array([kf.x[:3].flatten() for kf in self.kalman_filters])

        else:
            # Nếu không thấy tay
            self.frames_without_hand += 1
            if self.frames_without_hand >= self.RESET_THRESHOLD:
                # Nếu mất dấu quá lâu, reset bộ lọc
                self.is_kalman_initialized = False
        
        # Áp dụng ràng buộc xương lên các điểm đã lọc Kalman
        if self.is_calibrated and self.is_kalman_initialized:
            final_landmarks = self.apply_bone_constraints(final_landmarks)

        # Vẽ bàn tay đã lọc lên frame
        self.draw_kalman_hand(frame, final_landmarks)
        
        # Lấy vị trí cổ tay (đã lọc) để điều khiển búa
        wrist_pos_norm = final_landmarks[self.mp_hands.HandLandmark.WRIST]
        h, w, _ = frame.shape
        rehab_data['hand_pos'] = (int(np.clip(wrist_pos_norm[0], 0, 1) * w), 
                                  int(np.clip(wrist_pos_norm[1], 0, 1) * h))

        # Tính toán góc gập (flexion) nếu đã hiệu chỉnh
        if self.is_calibrated:
            flexion_angles = {}
            for name, (p1_idx, p2_idx, p3_idx) in self.ANGLES_TO_MEASURE_DEF.items():
                # Lấy góc từ các điểm đã lọc
                smooth_angle = self._hpr_angle(final_landmarks[p1_idx], final_landmarks[p2_idx], final_landmarks[p3_idx])
                
                # (SỬA) Góc gập = Góc duỗi tối đa - Góc hiện tại
                # Với cách đo mới này, Góc duỗi (xòe thẳng) sẽ RẤT LỚN (gần 180 độ)
                # và Góc hiện tại (nắm tay) sẽ NHỎ (ví dụ 30-90 độ)
                # => Kết quả sẽ là một số DƯƠNG LỚN (ví dụ 180 - 90 = 90 độ)
                flexion_angles[name] = max(0, self.angle_extended_dict[name] - smooth_angle)
            rehab_data['angles'] = flexion_angles
        
        rehab_data['is_calibrated'] = self.is_calibrated

        return frame, rehab_data, hand_landmarks_list

    def draw_kalman_hand(self, frame, landmarks_array):
        """Vẽ bàn tay bằng cách chuyển đổi mảng numpy về định dạng của MediaPipe."""
        if not self.is_kalman_initialized:
             return 
             
        landmarks_for_drawing = []
        for lm_pos in landmarks_array:
            landmark = landmark_pb2.NormalizedLandmark()
            landmark.x = lm_pos[0]
            landmark.y = lm_pos[1]
            landmark.z = lm_pos[2]
            landmarks_for_drawing.append(landmark)
        
        hand_landmarks_proto = landmark_pb2.NormalizedLandmarkList()
        hand_landmarks_proto.landmark.extend(landmarks_for_drawing)
        
        # Vẽ các điểm và đường nối
        self.mp_draw.draw_landmarks(
            frame, hand_landmarks_proto, self.mp_hands.HAND_CONNECTIONS)

    def _get_default_rehab_data(self):
        """Trả về dữ liệu rỗng khi không phát hiện tay hoặc chưa hiệu chỉnh"""
        default_angles = {name: 0.0 for name in self.FINGERS_LIST}
        # Đảm bảo các danh sách này khớp với định nghĩa ở hàm __init__
        default_lengths = {name: 0.0 for name in self.BONE_NAMES_LIST}
        default_ratios = {name: 0.0 for name in self.BONE_NAMES_LIST}
        
        return {
            'angles': default_angles, 
            'bone_lengths': default_lengths,
            'bone_ratios': default_ratios,
            'is_outlier': False,
            'is_calibrated': self.is_calibrated, # Trả về trạng thái hiệu chỉnh
            'hand_pos': None
        }