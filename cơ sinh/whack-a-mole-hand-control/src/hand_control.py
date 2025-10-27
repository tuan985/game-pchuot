import cv2
import mediapipe as mp
import numpy as np
import time
import math

class HandController:
    """
    Lớp HandController ĐÃ NÂNG CẤP để phục hồi chức năng.
    
    Tích hợp logic hiệu chỉnh, phát hiện ngoại lai, và đo góc mượt mà
    CHO CẢ 5 NGÓN TAY.
    
    (MỚI) Tự động tính toán và trả về độ dài + tỷ lệ các khớp.
    """
    
    def __init__(self, max_hands=1, min_detection_confidence=0.6, min_tracking_confidence=0.5):
        # --- MediaPipe Init ---
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

        # --- Camera Init ---
        self.cap = None

        # --- Trạng thái (State) của Bộ xử lý ---
        self.static_profile = {}             
        self.angle_extended_dict = {}    
        self.smoothed_angle_dict = {}    
        self.is_calibrated = False           

        # --- Cài đặt (Settings) ---
        self.EMA_ALPHA = 0.3            
        # Tăng ngưỡng để giảm nhiễu khi nắm tay
        self.OUTLIER_THRESHOLD = 0.35 
        
        # --- Định nghĩa các Điểm mốc (Landmark Definitions) ---
        self.FINGERS_LIST = ["thumb", "index", "middle", "ring", "pinky"]
        
        self.REFERENCE_BONES = (
            self.mp_hands.HandLandmark.INDEX_FINGER_MCP, 
            self.mp_hands.HandLandmark.PINKY_MCP
        ) 
        
        self.ANGLES_TO_MEASURE_DEF = {
            'index': (self.mp_hands.HandLandmark.WRIST, self.mp_hands.HandLandmark.INDEX_FINGER_MCP, self.mp_hands.HandLandmark.INDEX_FINGER_PIP),
            'middle': (self.mp_hands.HandLandmark.WRIST, self.mp_hands.HandLandmark.MIDDLE_FINGER_MCP, self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP),
            'ring': (self.mp_hands.HandLandmark.WRIST, self.mp_hands.HandLandmark.RING_FINGER_MCP, self.mp_hands.HandLandmark.RING_FINGER_PIP),
            'pinky': (self.mp_hands.HandLandmark.WRIST, self.mp_hands.HandLandmark.PINKY_MCP, self.mp_hands.HandLandmark.PINKY_PIP),
            'thumb': (self.mp_hands.HandLandmark.THUMB_MCP, self.mp_hands.HandLandmark.THUMB_IP, self.mp_hands.HandLandmark.THUMB_TIP),
        }
        
        # (MỚI) Đổi tên để dễ truy cập
        self.BONE_INDICES_TO_MONITOR = {
            'index_mcp': (self.mp_hands.HandLandmark.INDEX_FINGER_MCP, self.mp_hands.HandLandmark.INDEX_FINGER_PIP),
            'index_pip': (self.mp_hands.HandLandmark.INDEX_FINGER_PIP, self.mp_hands.HandLandmark.INDEX_FINGER_DIP),
            'middle_mcp': (self.mp_hands.HandLandmark.MIDDLE_FINGER_MCP, self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP),
            'middle_pip': (self.mp_hands.HandLandmark.MIDDLE_FINGER_PIP, self.mp_hands.HandLandmark.MIDDLE_FINGER_DIP),
            'ring_mcp': (self.mp_hands.HandLandmark.RING_FINGER_MCP, self.mp_hands.HandLandmark.RING_FINGER_PIP),
            'pinky_mcp': (self.mp_hands.HandLandmark.PINKY_MCP, self.mp_hands.HandLandmark.PINKY_PIP),
        }
        # (MỚI) Tạo danh sách tên xương để lặp
        self.BONE_NAMES_LIST = list(self.BONE_INDICES_TO_MONITOR.keys())

    # === CÁC HÀM QUẢN LÝ CAMERA (Giữ nguyên) ===
    def start_detection(self, src=0, width=640, height=480):
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
        try:
            if self.cap is not None:
                self.cap.release(); self.cap = None; print("Camera đã đóng")
        finally:
            cv2.destroyAllWindows(); self.hands.close()

    # === CÁC HÀM HỖ TRỢ TÍNH TOÁN (ĐÃ NÂNG CẤP) ===
    def _hpr_distance(self, p1, p2):
        return np.linalg.norm(p1 - p2)

    def _hpr_angle(self, p1, p2, p3):
        v1 = p1 - p2; v2 = p3 - p2
        dot_product = np.dot(v1, v2)
        norm_product = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm_product == 0: return 180.0
        cosine_angle = np.clip(dot_product / norm_product, -1.0, 1.0)
        return np.degrees(np.arccos(cosine_angle))

    def _hpr_landmarks_to_array(self, landmark_list):
        return np.array([[lm.x, lm.y, lm.z] for lm in landmark_list])

    def _hpr_get_current_biomechanics(self, landmarks):
        """
        (MỚI) Hàm này tính toán độ dài, tỷ lệ VÀ phát hiện ngoại lai.
        Trả về: (dict_lengths, dict_ratios, bool_is_outlier)
        """
        current_lengths = {}
        current_ratios = {}
        is_outlier = False
        
        try:
            # 1. Lấy "thước đo" của khung hình hiện tại
            p_ref_1 = landmarks[self.REFERENCE_BONES[0]]
            p_ref_2 = landmarks[self.REFERENCE_BONES[1]]
            L_ref_current = self._hpr_distance(p_ref_1, p_ref_2)
            
            if L_ref_current < 1e-6: # Gần như bằng 0
                is_outlier = True
                # Trả về dữ liệu rỗng nếu không có thước đo
                for name in self.BONE_NAMES_LIST:
                    current_lengths[name] = 0.0
                    current_ratios[name] = 0.0
                return current_lengths, current_ratios, is_outlier

            # 2. Tính toán và kiểm tra từng xương
            for name in self.BONE_NAMES_LIST:
                p1_idx, p2_idx = self.BONE_INDICES_TO_MONITOR[name]
                length = self._hpr_distance(landmarks[p1_idx], landmarks[p2_idx])
                ratio = length / L_ref_current
                
                current_lengths[name] = length
                current_ratios[name] = ratio
                
                # 3. So sánh độ sai lệch (nếu đã hiệu chỉnh)
                if self.is_calibrated:
                    static_ratio = self.static_profile.get(name, ratio) # Lấy tỷ lệ tĩnh
                    deviation = abs(ratio - static_ratio) / static_ratio
                    if deviation > self.OUTLIER_THRESHOLD:
                        is_outlier = True # Chỉ cần 1 xương sai là báo ngoại lai
            
            return current_lengths, current_ratios, is_outlier
        
        except Exception:
            # Trả về rỗng nếu có lỗi
            for name in self.BONE_NAMES_LIST:
                current_lengths[name] = 0.0
                current_ratios[name] = 0.0
            return current_lengths, current_ratios, True 

    # === CÁC HÀM CHỨC NĂNG CHÍNH (Đã nâng cấp) ===

    def calibrate(self, hand_landmarks_result):
        """
        Chạy hiệu chỉnh. Yêu cầu bệnh nhân XÒE THẲNG TAY.
        Lưu hồ sơ tĩnh VÀ góc duỗi thẳng cho CẢ 5 NGÓN.
        """
        print("Đang hiệu chỉnh... Vui lòng xòe thẳng tay!")
        landmarks = self._hpr_landmarks_to_array(hand_landmarks_result.landmark)
        
        try:
            # 1. THIẾT LẬP THƯỚC ĐO CHUẨN (L_ref)
            p_ref_1 = landmarks[self.REFERENCE_BONES[0]]
            p_ref_2 = landmarks[self.REFERENCE_BONES[1]]
            L_ref = self._hpr_distance(p_ref_1, p_ref_2)
            
            if L_ref < 1e-6:
                print("Lỗi hiệu chỉnh: Không thể lấy thước đo chuẩn. Thử lại.")
                return False

            # 2. THU THẬP THÔNG SỐ TĨNH (TỶ LỆ XƯƠNG)
            self.static_profile = {} 
            for name in self.BONE_NAMES_LIST:
                p1_idx, p2_idx = self.BONE_INDICES_TO_MONITOR[name]
                length = self._hpr_distance(landmarks[p1_idx], landmarks[p2_idx])
                self.static_profile[name] = length / L_ref # Lưu tỷ lệ

            # 3. THIẾT LẬP MỐC 0% (GÓC DUỖI) CHO CẢ 5 NGÓN
            self.angle_extended_dict = {}
            self.smoothed_angle_dict = {}
            
            for name, (p1_idx, p2_idx, p3_idx) in self.ANGLES_TO_MEASURE_DEF.items():
                angle = self._hpr_angle(landmarks[p1_idx], landmarks[p2_idx], landmarks[p3_idx])
                self.angle_extended_dict[name] = angle
                self.smoothed_angle_dict[name] = angle 

            self.is_calibrated = True
            print(f"...Hiệu chỉnh thành công! Hồ sơ tĩnh đã lưu.")
            return True
        
        except Exception as e:
            print(f"Lỗi hiệu chỉnh: {e}")
            self.is_calibrated = False
            return False

    def get_frame_data(self):
        """
        Hàm chính. Đọc frame, xử lý, và trả về dữ liệu phục hồi chức năng.
        
        Returns: (frame, rehab_data, hand_landmarks_object)
            - frame: ảnh BGR đã vẽ
            - rehab_data: dict {
                'angles': dict, 
                'bone_lengths': dict, 
                'bone_ratios': dict,
                'is_outlier': bool, 
                'is_calibrated': bool,
                'hand_pos': (x,y)
            }
            - hand_landmarks_object: Đối tượng landmarks thô (dùng để hiệu chỉnh)
        """
        if self.cap is None or not self.cap.isOpened():
            return None, self._get_default_rehab_data(), None

        success, frame = self.cap.read()
        if not success or frame is None:
            return None, self._get_default_rehab_data(), None

        frame = cv2.flip(frame, 1) # Lật ngang
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb_frame)

        rehab_data = self._get_default_rehab_data()
        hand_landmarks_object = None

        if results.multi_hand_landmarks:
            hand_landmarks_object = results.multi_hand_landmarks[0]
            self.mp_draw.draw_landmarks(frame, hand_landmarks_object, self.mp_hands.HAND_CONNECTIONS)
            
            try:
                wpt = hand_landmarks_object.landmark[self.mp_hands.HandLandmark.WRIST]
                rehab_data['hand_pos'] = (int(wpt.x * frame.shape[1]), int(wpt.y * frame.shape[0]))
            except Exception:
                pass 
            
            landmarks_arr = self._hpr_landmarks_to_array(hand_landmarks_object.landmark)

            # (MỚI) Lấy thông tin cơ sinh học (dài, tỷ lệ, ngoại lai)
            lengths, ratios, is_outlier = self._hpr_get_current_biomechanics(landmarks_arr)
            rehab_data['bone_lengths'] = lengths
            rehab_data['bone_ratios'] = ratios
            rehab_data['is_outlier'] = is_outlier

            # Tính toán góc (chỉ khi đã hiệu chỉnh)
            if self.is_calibrated:
                flexion_angles = {}
                for name in self.FINGERS_LIST:
                    (p1_idx, p2_idx, p3_idx) = self.ANGLES_TO_MEASURE_DEF[name]
                    
                    if not is_outlier:
                        raw_angle = self._hpr_angle(landmarks_arr[p1_idx], landmarks_arr[p2_idx], landmarks_arr[p3_idx])
                        self.smoothed_angle_dict[name] = (self.EMA_ALPHA * raw_angle) + \
                                                         ((1.0 - self.EMA_ALPHA) * self.smoothed_angle_dict[name])
                    
                    flex_angle = self.angle_extended_dict[name] - self.smoothed_angle_dict[name]
                    flexion_angles[name] = max(0, flex_angle) 
                
                rehab_data['angles'] = flexion_angles
            
        return frame, rehab_data, hand_landmarks_object
    
    def _get_default_rehab_data(self):
        """Trả về dữ liệu rỗng khi không phát hiện tay hoặc chưa hiệu chỉnh"""
        default_angles = {name: 0.0 for name in self.FINGERS_LIST}
        default_lengths = {name: 0.0 for name in self.BONE_NAMES_LIST}
        default_ratios = {name: 0.0 for name in self.BONE_NAMES_LIST}
        
        return {
            'angles': default_angles, 
            'bone_lengths': default_lengths,
            'bone_ratios': default_ratios,
            'is_outlier': False,
            'is_calibrated': self.is_calibrated,
            'hand_pos': None
        }