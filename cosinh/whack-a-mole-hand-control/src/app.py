# ==========================================================
# FILE: app.py
# PHIÊN BẢN: Đã làm sạch + THÊM TÍNH NĂNG FILE MASTER
# ==========================================================

import pygame
import random
import sys
import os
import cv2
import time
import numpy as np 
from datetime import datetime

# Import file hand_control.py
from hand_control import HandController 

# Thử import thư viện utils.py (nếu có)
try:
    from utils import load_image
except ImportError:
    print("Canh bao: Khong tim thay file 'utils.py'.")
    print("Dang su dung ham load_image mac dinh.")
    # Hàm load_image thay thế nếu không có utils.py
    def load_image(filename, size=None):
        try:
            image = pygame.image.load(filename)
            if size:
                image = pygame.transform.scale(image, size)
            return image
        except Exception as e:
            print(f"LOI: Khong the tai hinh anh '{filename}'. {e}")
            # Trả về một surface màu đen nếu lỗi
            surface = pygame.Surface(size if size else (100, 100))
            surface.fill((0, 0, 0))
            return surface

# Kiểm tra thư viện lưu Excel
try:
    from openpyxl import Workbook, load_workbook
    OPENPYXL = True
except ImportError:
    OPENPYXL = False
    print("Canh bao: Thu vien 'openpyxl' chua duoc cai dat.")
    print("Chuc nang luu file Excel se bi vo hieu hoa.")
    print("De cai dat, chay: pip install openpyxl")


pygame.init()

# --- KÍCH THƯỚC MÀN HÌNH ---
SCREEN_WIDTH = 900
SCREEN_HEIGHT = 800
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Game Đập Chuột Phục Hồi Chức Năng")

clock = pygame.time.Clock()
FPS = 60 # Đồng bộ FPS với dt của Kalman Filter

# --- CÀI ĐẶT ĐỘ KHÓ ---
DIFFICULTY_PRESETS = {
    "easy":   {"spawn_den": 240, "min_up": 2000, "max_up": 3500, "max_simultaneous": 2},
    "normal": {"spawn_den": 120, "min_up": 1000, "max_up": 2500, "max_simultaneous": 3},
    "hard":   {"spawn_den": 60,  "min_up": 700,  "max_up": 1800, "max_simultaneous": 4},
}
DIFFICULTY = "easy"
_spawn_cfg = DIFFICULTY_PRESETS[DIFFICULTY]
SPAWN_DENOM = _spawn_cfg["spawn_den"]
MOLE_UP_MIN_MS = _spawn_cfg["min_up"]
MOLE_UP_MAX_MS = _spawn_cfg["max_up"]
MAX_SIMULTANEOUS_MOLES = _spawn_cfg["max_simultaneous"]

# --- MÀU ---
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (0, 150, 0)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
CYAN = (0, 255, 255)

# --- PHÔNG CHỮ ---
try:
    font = pygame.font.SysFont("arial", 64)
    small_font = pygame.font.SysFont("arial", 32)
    tiny_font = pygame.font.SysFont("arial", 18)
except Exception:
    print("Loi font 'arial', su dung font mac dinh.")
    font = pygame.font.Font(None, 74)
    small_font = pygame.font.Font(None, 42)
    tiny_font = pygame.font.Font(None, 24)


# --- TẢI HÌNH ẢNH ---
base_dir = os.path.dirname(__file__) # Thư mục chứa file app.py
BACKGROUND_IMAGE = load_image(os.path.join(base_dir, 'background.png'), (SCREEN_WIDTH, SCREEN_HEIGHT))
HOLE_IMAGE = load_image(os.path.join(base_dir, 'hole.png'), (150, 100))
MOLE_IMAGE_UP = load_image(os.path.join(base_dir, 'mole.png'), (100, 100))
MOLE_IMAGE_DOWN = load_image(os.path.join(base_dir, 'hit_mole.png'), (100, 100))
HAMMER_IMAGE = load_image(os.path.join(base_dir, 'hammer.png'), (80, 80))

# --- CÁC HÀM LƯU DỮ LIỆU EXCEL ---
# Các danh sách này phải khớp với định nghĩa trong hand_control.py
FINGERS_LIST = ["thumb", "index", "middle", "ring", "pinky"]
BONE_NAMES_LIST = ['index_mcp', 'index_pip', 'middle_mcp', 'middle_pip', 'ring_mcp', 'pinky_mcp']

# Biến toàn cục để lưu tên file của phiên làm việc
ANGLES_XLSX_SESSION = ""
ANGLES_SUMMARY_XLSX_SESSION = ""
CALIBRATION_XLSX_SESSION = ""
# ==========================================================
# (MỚI) Tên file MASTER để gộp chung tất cả dữ liệu
MASTER_ANGLES_FILE = os.path.join(os.path.dirname(__file__), "game_angles_detailed_MASTER.xlsx")
# ==========================================================


def ensure_angles_xlsx(filename):
    """
    Tạo file Excel chi tiết (detailed) nếu nó chưa tồn tại.
    Hàm này tạo ra hàng tiêu đề (header).
    """
    if not OPENPYXL or os.path.exists(filename): 
        return
        
    wb = Workbook(); ws = wb.active
    
    # === HÀNG TIÊU ĐỀ QUAN TRỌNG (PHIÊN BẢN ĐÚNG) ===
    header = ["timestamp", "is_outlier", "is_calibrated"]
    # Thêm cột góc
    for f in FINGERS_LIST: 
        header.append(f"{f}_angle") # Sửa lỗi: "angl" -> "angle"
    # Thêm cột độ dài (length)
    for b in BONE_NAMES_LIST: 
        header.append(f"{b}_len")   # Thêm "_len"
    # Thêm cột tỷ lệ (ratio)
    for b in BONE_NAMES_LIST: 
        header.append(f"{b}_ratio") # Thêm "_ratio"
    # ================================
    
    ws.append(header)
    try:
        wb.save(filename)
    except Exception as e:
        print(f"LOI khi tao file Excel chi tiet: {e}")

def save_angles_xlsx_batch(rehab_list, filename):
    """
    Lưu toàn bộ dữ liệu từ bộ đệm (rehab_list) vào file Excel một lần.
    Hàm này giờ sẽ MỞ file, GHI THÊM, rồi LƯU LẠI.
    """
    if not OPENPYXL:
        print("Bo qua luu file chi tiet (thieu openpyxl).")
        return
    if not rehab_list:
        print(f"Khong co du lieu chi tiet de luu vao file {os.path.basename(filename)} (bo dem rong).")
        return
    
    print(f"Dang luu {len(rehab_list)} dong du lieu chi tiet vao {os.path.basename(filename)}...")
    
    # Đảm bảo file tồn tại (phòng trường hợp bị xóa)
    ensure_angles_xlsx(filename) 
    
    try:
        wb = load_workbook(filename)
        ws = wb.active
    except Exception as e:
        print(f"LOI khi mo file Excel chi tiet: {e}. Thu tao file backup.")
        try:
            filename_backup = filename.replace(".xlsx", f"_{datetime.now().strftime('%H%M%S')}_backup.xlsx")
            ensure_angles_xlsx(filename_backup)
            wb = load_workbook(filename_backup)
            ws = wb.active
            filename = filename_backup # Dùng file backup từ giờ
        except Exception as e2:
            print(f"LOI: Khong the mo file backup. {e2}. Bo qua viec luu.")
            return

    # Lặp qua từng mục dữ liệu trong bộ đệm
    for rehab_data in rehab_list:
        ts = rehab_data.get("timestamp") or datetime.now().isoformat()
        
        # Lấy dữ liệu từ từ điển rehab_data
        angles = rehab_data.get("angles", {})
        lengths = rehab_data.get("bone_lengths", {}) # Phải khớp với 'bone_lengths' từ hand_control
        ratios = rehab_data.get("bone_ratios", {}) # Phải khớp với 'bone_ratios' từ hand_control
        
        row = [
            ts, 
            rehab_data.get("is_outlier", False), 
            rehab_data.get("is_calibrated", False)
        ]
        
        # Ghi dữ liệu vào hàng (row)
        for f in FINGERS_LIST: 
            row.append(angles.get(f, 0))
        for b in BONE_NAMES_LIST: 
            row.append(lengths.get(b, 0)) # Lấy từ 'lengths'
        for b in BONE_NAMES_LIST: 
            row.append(ratios.get(b, 0)) # Lấy từ 'ratios'
            
        ws.append(row)
    
    try:
        wb.save(filename)
        print(f"Luu file {os.path.basename(filename)} thanh cong.")
    except Exception as e:
        print(f"LOI khi luu file Excel {os.path.basename(filename)}: {e} (Hay dam bao file da dong)")

# ... (Các hàm ensure_angles_summary_xlsx, save_angles_summary_xlsx, save_static_profile giữ nguyên) ...
def ensure_angles_summary_xlsx(filename):
    """Tạo file tóm tắt (summary) nếu chưa có."""
    if not OPENPYXL or os.path.exists(filename): return
    wb = Workbook(); ws = wb.active; ws.title = "Summary"
    header = ["timestamp", "player", "round", "frames_recorded"]
    for f in FINGERS_LIST: header += [f"{f}_avg", f"{f}_max", f"{f}_min"]
    header += ["outlier_count", "outlier_percentage"]; ws.append(header)
    try:
        wb.save(filename)
    except Exception as e:
        print(f"LOI khi tao file Excel tom tat: {e}")

def save_angles_summary_xlsx(player, round_no, stats, filename):
    """Lưu tóm tắt của 1 lượt chơi."""
    if not OPENPYXL: 
        print("Bo qua luu file tom tat (thieu openpyxl).")
        return
        
    print(f"Dang luu file tom tat cho {player}, luot {round_no}...")
    ensure_angles_summary_xlsx(filename) 
    
    try:
        wb = load_workbook(filename); ws = wb.active
    except Exception as e:
        print(f"LOI khi mo file Excel tom tat: {e}. Bo qua.")
        return
        
    ts = datetime.now().isoformat()
    frames_count = stats.get('index', {}).get("count", 0)
    row = [ts, player, round_no, frames_count]
    
    for f in FINGERS_LIST:
        s = stats.get(f, {"count": 0, "sum": 0.0, "max": 0.0, "min": 999.0})
        cnt = s.get("count", 0); avg = (s.get("sum", 0.0) / cnt) if cnt > 0 else 0.0
        mx = s.get("max", 0.0); mn = s.get("min", 999.0) if cnt > 0 else 0.0
        row += [round(avg, 1), round(mx, 1), round(mn, 1)]
        
    outlier_cnt = stats.get("outlier_count", 0)
    outlier_pct = (outlier_cnt / frames_count * 100) if frames_count > 0 else 0.0
    row += [outlier_cnt, round(outlier_pct, 1)]
    
    ws.append(row)
    try:
        wb.save(filename)
        print("Luu file tom tat thanh cong.")
    except Exception as e:
         print(f"LOI khi luu file Excel tom tat: {e} (Hay dam bao file da dong)")

def save_static_profile(hand_controller, filename):
    if not OPENPYXL:
        print("Loi: Thieu thu vien openpyxl. Khong luu ho so tinh.")
        return
    if not hand_controller.is_calibrated:
        print("Loi: Chua hieu chinh. Khong luu ho so tinh.")
        return
        
    print(f"Dang luu Ho So Tinh (Calibration Profile) vao {os.path.basename(filename)}...")
    wb = Workbook()
    
    # Sheet 1: Tỷ lệ xương
    ws_profile = wb.active
    ws_profile.title = "Static Bone Ratios"
    ws_profile.append(["Bone", "Calibrated Ratio (Tuong doi voi L_ref)"])
    if not hand_controller.static_profile:
        print("CANH BAO: Ho so tinh (ty le) bi rong.")
    for bone_name, ratio in hand_controller.static_profile.items():
        ws_profile.append([bone_name, ratio])
        
    # Sheet 2: Góc duỗi
    ws_angles = wb.create_sheet(title="Extended Angles")
    ws_angles.append(["Finger", "Calibrated Extended Angle (Do)"])
    if not hand_controller.angle_extended_dict:
        print("CANH BAO: Ho so tinh (goc) bi rong.")
    for finger_name, angle in hand_controller.angle_extended_dict.items():
        ws_angles.append([finger_name, angle])
        
    try:
        wb.save(filename)
        print("Luu Ho So Tinh thanh cong.")
    except Exception as e:
        print(f"LOI khi luu Ho So Tinh: {e} (Hay dam bao file da dong)")
# ==========================================================

# ... (Class Mole, save_score_to_excel, draw_button, get_player_info, show_calibration_screen giữ nguyên) ...
class Mole(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image_up = MOLE_IMAGE_UP
        self.image_down_hit = MOLE_IMAGE_DOWN
        self.hole_image = HOLE_IMAGE
        self.image = self.hole_image # Bắt đầu bằng hình cái hang
        
        # Đặt tâm của cái hang tại (x, y)
        self.rect = self.hole_image.get_rect(center=(x, y))
        
        self.is_up = False
        self.hit = False
        self.time_up = 0 # Thời điểm trồi lên
        self.hit_display_time = 300 # Thời gian hiển thị hình ảnh "đã bị đập"
        self.time_hit = 0 # Thời điểm bị đập
        self.up_duration = random.randint(MOLE_UP_MIN_MS, MOLE_UP_MAX_MS) # Thời gian trồi lên
        
    def show(self):
        """Cho chuột trồi lên."""
        if not self.is_up:
            self.is_up = True
            self.hit = False
            self.time_up = pygame.time.get_ticks()
            self.up_duration = random.randint(MOLE_UP_MIN_MS, MOLE_UP_MAX_MS)
            # Điều chỉnh vị trí của chuột để nó nằm giữa cái hang
            self.image = self.image_up
            self.rect = self.image.get_rect(center=self.rect.center)
            
    def update(self):
        """Cập nhật trạng thái của chuột (ẩn đi nếu hết giờ)."""
        now = pygame.time.get_ticks()
        if self.is_up:
            if self.hit:
                # Nếu đã bị đập, ẩn đi sau 0.3 giây
                if now - self.time_hit > self.hit_display_time:
                    self.is_up = False
                    self.image = self.hole_image
                    self.rect = self.hole_image.get_rect(center=self.rect.center)
            elif now - self.time_up > self.up_duration:
                # Nếu hết giờ mà chưa bị đập, ẩn đi
                self.is_up = False
                self.image = self.hole_image
                self.rect = self.hole_image.get_rect(center=self.rect.center)
                
    def was_hit(self):
        """Xử lý khi chuột bị đập."""
        global score, hit_count
        if self.is_up and not self.hit:
            self.hit = True
            self.image = self.image_down_hit
            self.rect = self.image_down_hit.get_rect(center=self.rect.center)
            self.time_hit = pygame.time.get_ticks()
            score += 10
            hit_count += 1
            return True
        return False

def save_score_to_excel(player_name, score, hit_count, accuracy, filename="game_history.xlsx"):
    if not OPENPYXL: return
    file_path = os.path.join(os.path.dirname(__file__), filename) 
    
    if not os.path.exists(file_path):
        wb = Workbook(); ws = wb.active; ws.title = "LichSu"
        ws.append(["Thời gian", "Tên người chơi", "Điểm", "Số lần trúng", "Tỉ lệ phản ứng (%)"])
        try:
            wb.save(file_path)
        except Exception as e:
            print(f"LOI khi tao file lich su: {e}")
            return
            
    try:
        wb = load_workbook(file_path); ws = wb.active
    except Exception as e:
        print(f"LOI khi mo file lich su: {e}")
        return
        
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.append([now, player_name, score, hit_count, round(accuracy, 1)])
    try:
        wb.save(file_path); print(f"✅ Đã lưu kết quả của {player_name} vào {filename}")
    except Exception as e:
        print(f"LOI khi luu file lich su: {e}")

def draw_button(surface, rect, text, font, bg_color, text_color):
    pygame.draw.rect(surface, bg_color, rect, border_radius=10)
    label = font.render(text, True, text_color)
    surface.blit(label, (rect.x + (rect.width - label.get_width()) // 2,
                         rect.y + (rect.height - label.get_height()) // 2))

def get_player_info():
    """Màn hình nhập tên và số lượt chơi."""
    pygame.mouse.set_visible(True)
    pygame.key.start_text_input()
    
    player_name = ""; num_games = ""; stage = "name" # 'name' hoặc 'num'
    input_active = True
    
    while input_active:
        start_button = pygame.Rect(SCREEN_WIDTH // 2 - 100, 400, 200, 60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.key.stop_text_input(); pygame.quit(); sys.exit()
                
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN: # Phím Enter
                    if stage == "name" and player_name.strip(): 
                        stage = "num"
                    elif stage == "num" and num_games.strip().isdigit(): 
                        input_active = False
                elif event.key == pygame.K_BACKSPACE: # Phím Xóa
                    if stage == "name": player_name = player_name[:-1]
                    else: num_games = num_games[:-1]
                elif event.key == pygame.K_ESCAPE:
                    pygame.key.stop_text_input(); pygame.quit(); sys.exit()
                else:
                    # Nhập văn bản
                    if stage == "name" and len(player_name) < 15: 
                        player_name += event.unicode
                    elif stage == "num" and event.unicode.isdigit() and len(num_games) < 2: 
                        num_games += event.unicode
                        
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if start_button.collidepoint(event.pos):
                    if stage == "name" and player_name.strip(): 
                        stage = "num"
                    elif stage == "num" and num_games.strip().isdigit(): 
                        input_active = False
                        
        screen.blit(BACKGROUND_IMAGE, (0, 0))
        
        title = "NHAP TEN NGUOI CHOI:" if stage == "name" else "NHAP SO LAN CHOI:"
        current_text = player_name if stage == "name" else num_games
        
        text_surface = font.render(title, True, WHITE)
        screen.blit(text_surface, (SCREEN_WIDTH // 2 - text_surface.get_width() // 2, 180))
        
        input_surface = small_font.render(current_text + "|", True, GREEN) # Thêm dấu "|" nhấp nháy
        screen.blit(input_surface, (SCREEN_WIDTH // 2 - input_surface.get_width() // 2, 300))
        
        draw_button(screen, start_button, "TIEP TUC", small_font, GREEN, WHITE)
        
        pygame.display.flip(); clock.tick(30)
        
    pygame.key.stop_text_input(); pygame.mouse.set_visible(False)
    
    # Trả về tên và số lượt chơi (mặc định là 1 nếu nhập sai)
    return player_name, int(num_games) if num_games.strip().isdigit() and int(num_games) > 0 else 1

def show_calibration_screen(hand_controller):
    """Màn hình đếm ngược để hiệu chỉnh tay."""
    calibrated = False; countdown_start_time = None; countdown_duration_sec = 3
    
    while not calibrated:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                hand_controller.stop_detection(); pygame.quit(); sys.exit()
                
        # Lấy dữ liệu camera
        cam_frame, rehab_data, hand_landmarks = hand_controller.get_frame_data()
        
        if cam_frame is None: 
            # Xử lý nếu camera bị lỗi
            cam_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(cam_frame, "LOI CAMERA", (100, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)

        screen.blit(BACKGROUND_IMAGE, (0, 0))
        
        # Vẽ khung camera lên màn hình game
        cam_h, cam_w = 480, 640
        try:
            cam_frame_resized = cv2.resize(cam_frame, (cam_w, cam_h))
            cam_frame_rgb = cv2.cvtColor(cam_frame_resized, cv2.COLOR_BGR2RGB)
            cam_surface = pygame.surfarray.make_surface(cam_frame_rgb.swapaxes(0, 1))
            screen.blit(cam_surface, (SCREEN_WIDTH // 2 - cam_w // 2, SCREEN_HEIGHT // 2 - cam_h // 2 - 50))
        except Exception as e:
            print(f"Loi ve camera: {e}")
            
        current_time_ticks = pygame.time.get_ticks()
        
        text_surface = None # Khởi tạo
        
        if not hand_landmarks:
            # Nếu không thấy tay
            text_surface = small_font.render("Dua tay vao khung hinh...", True, YELLOW)
            countdown_start_time = None # Reset đếm ngược
        else:
            # Nếu thấy tay
            if countdown_start_time is None:
                # Bắt đầu đếm ngược
                countdown_start_time = current_time_ticks
                text_surface = small_font.render("Da thay tay! XOE THANG va GIU YEN...", True, WHITE)
            else:
                elapsed_sec = (current_time_ticks - countdown_start_time) / 1000.0
                time_left = countdown_duration_sec - int(elapsed_sec)
                
                if time_left > 0:
                    # Đang đếm ngược
                    text_surface = small_font.render(f"Giu yen tay... {time_left}", True, WHITE)
                else:
                    # Hết giờ, bắt đầu hiệu chỉnh
                    text_surface = small_font.render("Dang hieu chinh...", True, GREEN)
                    pygame.display.flip() # Hiển thị chữ "Dang hieu chinh..."
                    
                    if hand_controller.calibrate(hand_landmarks):
                        calibrated = True # Hiệu chỉnh thành công!
                        # LƯU HỒ SƠ TĨNH NGAY LẬP TỨC
                        save_static_profile(hand_controller, CALIBRATION_XLSX_SESSION)
                    else:
                        # Hiệu chỉnh thất bại
                        text_surface = small_font.render("Loi! Thu lai...", True, RED)
                        countdown_start_time = None
                        pygame.display.flip(); pygame.time.wait(1000) # Đợi 1 giây rồi thử lại
        
        if text_surface: # Chỉ vẽ nếu text đã được tạo
            screen.blit(text_surface, (SCREEN_WIDTH // 2 - text_surface.get_width() // 2, 100))
        pygame.display.flip(); clock.tick(FPS)
        
    # Hiệu chỉnh xong
    screen.blit(BACKGROUND_IMAGE, (0, 0))
    text_surface = font.render("DA SAN SANG!", True, GREEN)
    screen.blit(text_surface, (SCREEN_WIDTH // 2 - text_surface.get_width() // 2, 350))
    pygame.display.flip(); pygame.time.wait(2000) # Chờ 2 giây

# --- KHỞI TẠO GAME ---
# Vị trí các hang chuột (3x3)
base_x, base_y = 280, 300
x_spacing, y_spacing = 170, 150
mole_positions = [(base_x + i * x_spacing, base_y + j * y_spacing) for j in range(3) for i in range(3)]
moles = [Mole(x, y) for x, y in mole_positions]

# Khởi tạo bộ điều khiển tay
try:
    hand_controller = HandController()
    hand_controller.start_detection()
except Exception as e:
    print(f"LOI NGHIEM TRONG khi khoi tao HandController: {e}")
    pygame.quit()
    sys.exit()

# Biến kiểm soát cử chỉ (để không đập quá nhanh)
gesture_cooldown = 0.3 # 300ms
last_gesture_time = 0.0

# ==========================================================
# VÒNG LẶP TOÀN GAME (Quản lý các phiên chơi)
# ==========================================================
while True:
    
    # === TẠO TÊN FILE DUY NHẤT CHO PHIÊN CHƠI NÀY ===
    session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = os.path.dirname(__file__)
    
    # Gán tên file vào các biến toàn cục
    ANGLES_XLSX_SESSION = os.path.join(base_dir, f"game_angles_detailed_{session_timestamp}.xlsx")
    ANGLES_SUMMARY_XLSX_SESSION = os.path.join(base_dir, f"game_angles_summary_{session_timestamp}.xlsx")
    CALIBRATION_XLSX_SESSION = os.path.join(base_dir, f"calibration_profile_{session_timestamp}.xlsx")
    
    print("="*30)
    print(f"Phien lam viec moi: {session_timestamp}")
    print(f"File chi tiet (phien): {os.path.basename(ANGLES_XLSX_SESSION)}")
    print(f"File tom tat (phien): {os.path.basename(ANGLES_SUMMARY_XLSX_SESSION)}")
    print(f"File hieu chinh: {os.path.basename(CALIBRATION_XLSX_SESSION)}")
    print(f"File chi tiet (MASTER): {os.path.basename(MASTER_ANGLES_FILE)}")
    print("="*30)
    
    # Tạo các file Excel (với hàng tiêu đề) ngay lập tức
    ensure_angles_xlsx(ANGLES_XLSX_SESSION)
    ensure_angles_summary_xlsx(ANGLES_SUMMARY_XLSX_SESSION)
    # (MỚI) Đảm bảo file TỔNG (MASTER) cũng tồn tại
    ensure_angles_xlsx(MASTER_ANGLES_FILE)

    
    # Màn hình nhập tên và hiệu chỉnh
    player_name, total_rounds = get_player_info()
    show_calibration_screen(hand_controller) # Hàm này sẽ tự động lưu file calibration
    
    round_count = 0
    while round_count < total_rounds:
        # === KHỞI TẠO LƯỢT CHƠI MỚI ===
        score = 0; hit_count = 0; total_moles_shown = 0
        game_time_sec = 30; game_over = False
        start_time_ticks = pygame.time.get_ticks()

        # Bộ đệm để lưu dữ liệu của lượt chơi này
        angles_buffer = [] 
        # Biến thống kê cho file tóm tắt
        angle_stats = {f: {"count": 0, "sum": 0.0, "max": 0.0, "min": 999.0} for f in FINGERS_LIST}
        angle_stats["outlier_count"] = 0 

        running = True
        hammer_rect = None # Khởi tạo
        
        # ==========================================================
        # VÒNG LẶP MỘT LƯỢT CHƠI
        # ==========================================================
        while running:
            # --- Xử lý sự kiện (thoát game, click chuột khi game over) ---
            play_again_rect = pygame.Rect(SCREEN_WIDTH//2 - 100, 600, 200, 60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    hand_controller.stop_detection(); pygame.quit(); sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN and game_over:
                    pygame.mouse.set_visible(True)
                    if play_again_rect.collidepoint(event.pos):
                        running = False # Kết thúc lượt này, bắt đầu lượt tiếp
                        pygame.mouse.set_visible(False)
            
            # --- Lấy dữ liệu từ camera và tay ---
            cam_frame, rehab_data, hand_landmarks = hand_controller.get_frame_data()
            if cam_frame is None:
                # Xử lý nếu camera bị ngắt kết nối giữa chừng
                cam_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(cam_frame, "MAT KET NOI CAMERA", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)

            
            # --- CẬP NHẬT THỐNG KÊ (NẾU ĐÃ HIỆU CHỈNH) ---
            # PHẢI DÙNG CODE MỚI THÌ 'is_calibrated' MỚI LÀ TRUE
            if rehab_data['is_calibrated']:
                if rehab_data['is_outlier']: 
                    angle_stats["outlier_count"] += 1
                try:
                    # Thêm dữ liệu (bao gồm cả angles, bone_lengths, bone_ratios) vào bộ đệm
                    buf_entry = rehab_data.copy()
                    buf_entry['timestamp'] = datetime.now().isoformat()
                    angles_buffer.append(buf_entry) 
                except Exception as e: 
                    print(f"Loi them vao bo dem: {e}")
                
                # Cập nhật thống kê min/max/avg
                for f, val in rehab_data.get('angles', {}).items():
                    if f in angle_stats: 
                        s = angle_stats[f]; s["count"] += 1; s["sum"] += val
                        if val > s["max"]: s["max"] = val
                        if val < s["min"]: s["min"] = val

            # --- LOGIC GAME CHÍNH ---
            if not game_over:
                elapsed_sec = (pygame.time.get_ticks() - start_time_ticks) // 1000
                if elapsed_sec >= game_time_sec:
                    # Hết giờ
                    game_over = True
                    acc = (hit_count / total_moles_shown * 100) if total_moles_shown > 0 else 0
                    save_score_to_excel(player_name, score, hit_count, acc) # Lưu lịch sử
                    # Lưu file tóm tắt
                    save_angles_summary_xlsx(player_name, round_count + 1, angle_stats, ANGLES_SUMMARY_XLSX_SESSION)

                # Cập nhật trạng thái chuột (ẩn/hiện)
                for mole in moles:
                    mole.update()

                # Logic cho chuột trồi lên ngẫu nhiên
                up_count = sum(1 for m in moles if m.is_up)
                if up_count < MAX_SIMULTANEOUS_MOLES and random.randint(1, SPAWN_DENOM) == 1:
                    available = [m for m in moles if not m.is_up]
                    if available:
                        random.choice(available).show()
                        total_moles_shown += 1
                
                # ==========================================================
                # LOGIC ĐIỀU KHIỂN BẰNG TAY VÀ CỬ CHỈ
                # ==========================================================
                
                # 1. Lấy vị trí búa (đã lọc Kalman)
                hand_position = rehab_data['hand_pos'] 
                
                # 2. Logic "Đập" (Cử chỉ nắm tay)
                is_hitting_gesture = False
                now = time.time()
                angles_dict = rehab_data.get('angles', {})
                # Tính trung bình góc gập của 3 ngón (trỏ, giữa, nhẫn)
                avg_flex_angle = (angles_dict.get('index', 0) + angles_dict.get('middle', 0) + angles_dict.get('ring', 0)) / 3.0
                
                # Ngưỡng đập là 50 độ
                if rehab_data['is_calibrated'] and \
                   not rehab_data['is_outlier'] and \
                   avg_flex_angle > 30 and \
                   (now - last_gesture_time > gesture_cooldown): # Đảm bảo không đập quá nhanh
                    
                    is_hitting_gesture = True
                    last_gesture_time = now

                # 3. Vẽ búa và kiểm tra va chạm
                if hand_position:
                    # Tính toán vị trí tâm búa dựa trên vị trí cổ tay
                    hammer_x = hand_position[0] - HAMMER_IMAGE.get_width() // 2
                    hammer_y = hand_position[1] - HAMMER_IMAGE.get_height() // 2
                    hammer_rect = pygame.Rect(hammer_x, hammer_y, 
                                              HAMMER_IMAGE.get_width(), 
                                              HAMMER_IMAGE.get_height())
                    
                    # Chỉ kiểm tra va chạm NẾU có cử chỉ "đập" (is_hitting_gesture = True)
                    if is_hitting_gesture:
                        for mole in moles:
                            # Kiểm tra va chạm giữa hình chữ nhật của búa và chuột
                            if mole.rect.colliderect(hammer_rect):
                                mole.was_hit()
                # ==========================================================
                
            # --- VẼ MỌI THỨ LÊN MÀN HÌNH ---
            screen.blit(BACKGROUND_IMAGE, (0, 0))
            
            # Vẽ hang chuột (lớp dưới)
            for mole in moles:
                screen.blit(mole.hole_image, mole.hole_image.get_rect(center=mole.rect.center))
            
            # Vẽ chuột (lớp trên)
            for mole in moles:
                if mole.is_up:
                    screen.blit(mole.image, mole.rect)
            
            # Vẽ búa (nếu có vị trí tay)
            if hand_position and hammer_rect:
                screen.blit(HAMMER_IMAGE, hammer_rect)

            # Vẽ điểm số và thời gian
            score_text_surface = small_font.render(f"Score: {score}", True, BLACK)
            time_left = max(0, game_time_sec - (pygame.time.get_ticks() - start_time_ticks)//1000)
            time_text_surface = small_font.render(f"Time: {time_left}s", True, BLACK)
            screen.blit(score_text_surface, (10, 10))
            screen.blit(time_text_surface, (SCREEN_WIDTH - time_text_surface.get_width() - 10, 10))

            # --- Chuẩn bị khung camera nhỏ để hiển thị ---
            status_text = "DANG CHO TAY..."
            status_color = RED
            if hand_controller.is_calibrated: 
                status_text = "DANG DO..."
                status_color = GREEN
                if rehab_data['is_outlier']:
                    status_text = "TIN HIEU YEU (NHIEU)"
                    status_color = YELLOW
            
            angles_dict = rehab_data.get('angles', {})
            index_angle_display = angles_dict.get('index', 0.0)
            avg_angle_display = np.mean([v for k, v in angles_dict.items() if v > 0]) if any(v > 0 for k, v in angles_dict.items()) else 0.0
            
            angle_text_1 = f"Goc (Tro): {index_angle_display:.1f}"
            angle_text_2 = f"TBinh (5 ng.): {avg_angle_display:.1f}"
            
            # Vẽ text trạng thái lên khung camera
            cv2.putText(cam_frame, status_text, (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 1, cv2.LINE_AA)
            cv2.putText(cam_frame, angle_text_1, (5, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, CYAN, 1, cv2.LINE_AA)
            cv2.putText(cam_frame, angle_text_2, (5, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, CYAN, 1, cv2.LINE_AA)

            if game_over:
                # Vẽ màn hình Game Over
                pygame.mouse.set_visible(True) 
                overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA); overlay.fill((0, 0, 0, 180)); screen.blit(overlay, (0, 0))
                acc = (hit_count / total_moles_shown * 100) if total_moles_shown > 0 else 0
                texts = [
                    font.render("GAME OVER", True, RED),
                    small_font.render(f"Ten: {player_name}", True, WHITE),
                    small_font.render(f"Diem: {score}", True, WHITE),
                    small_font.render(f"So lan nam tay: {hit_count}", True, WHITE),
                    small_font.render(f"Ti le phan ung: {acc:.1f}%", True, WHITE)
                ]
                for i, t in enumerate(texts):
                    screen.blit(t, (SCREEN_WIDTH//2 - t.get_width()//2, 200 + i*60))
                
                # Vẽ nút "Lượt tiếp"
                draw_button(screen, play_again_rect, "LUOT TIEP", small_font, GREEN, WHITE)

            # Vẽ khung camera nhỏ (đã có text) lên màn hình game
            cam_h, cam_w = 150, 180
            cam_frame_resized = cv2.resize(cam_frame, (cam_w, cam_h))
            cam_frame_rgb = cv2.cvtColor(cam_frame_resized, cv2.COLOR_BGR2RGB)
            cam_surface = pygame.surfarray.make_surface(cam_frame_rgb.swapaxes(0, 1))
            screen.blit(cam_surface, (10, SCREEN_HEIGHT - cam_h - 10))

            # Cập nhật màn hình
            pygame.display.flip()
            clock.tick(FPS)
        
        # ==========================================================
        # KẾT THÚC MỘT LƯỢT CHƠI (running = False)
        # ==========================================================
        round_count += 1
        
        try:
            # (SỬA) LƯU VÀO CẢ 2 FILE
            
            # 1. Lưu vào file của phiên này (SESSION)
            print(f"--- Dang luu file cho phien: {os.path.basename(ANGLES_XLSX_SESSION)} ---")
            save_angles_xlsx_batch(angles_buffer, ANGLES_XLSX_SESSION)
            
            # 2. (MỚI) Lưu gộp vào file TỔNG (MASTER)
            print(f"--- Dang luu gop vao file MASTER: {os.path.basename(MASTER_ANGLES_FILE)} ---")
            save_angles_xlsx_batch(angles_buffer, MASTER_ANGLES_FILE)

        except Exception as e:
            print(f"Loi khi luu batch goc: {e}")

    # ==========================================================
    # KẾT THÚC TOÀN BỘ SỐ LƯỢT CHƠI
    # ==========================================================
    screen.fill(BLACK)
    msg = font.render("DA HOAN THANH!", True, RED)
    msg2 = small_font.render("An phim bat ky de choi lai", True, WHITE)
    screen.blit(msg, (SCREEN_WIDTH//2 - msg.get_width()//2, 300))
    screen.blit(msg2, (SCREEN_WIDTH//2 - msg2.get_width()//2, 400))
    pygame.display.flip()

    # Chờ người dùng nhấn phím để bắt đầu lại vòng lặp game
    waiting = True
    while waiting:
        pygame.mouse.set_visible(True) 
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                hand_controller.stop_detection(); pygame.quit(); sys.exit()
            elif event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
                waiting = False