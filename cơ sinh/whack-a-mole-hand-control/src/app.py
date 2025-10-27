import pygame
import random
import sys
import os
import cv2
import time # <-- THÊM IMPORT TIME
import numpy as np 
from hand_control import HandController 
try:
    from openpyxl import Workbook, load_workbook
    OPENPYXL = True
except ImportError:
    OPENPYXL = False
    print("Cảnh báo: Thư viện 'openpyxl' chưa được cài đặt. Chức năng lưu file Excel sẽ bị vô hiệu hóa.")
    print("Để cài đặt, chạy: pip install openpyxl")

from datetime import datetime

pygame.init()

# --- KÍCH THƯỚC MÀN HÌNH ---
SCREEN_WIDTH = 900
SCREEN_HEIGHT = 800
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Game Đập Chuột Phục Hồi Chức Năng")

clock = pygame.time.Clock()
FPS = 120

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
font = pygame.font.SysFont("arial", 64)
small_font = pygame.font.SysFont("arial", 32)
tiny_font = pygame.font.SysFont("arial", 18)

# --- HÀM LOAD ẢNH ---
def load_image(file_name, size=None):
    path = os.path.join('assets', file_name)
    image = pygame.image.load(path).convert_alpha()
    if size:
        image = pygame.transform.scale(image, size)
    return image

BACKGROUND_IMAGE = load_image('background.png', (SCREEN_WIDTH, SCREEN_HEIGHT))
HOLE_IMAGE = load_image('hole.png', (150, 100))
MOLE_IMAGE_UP = load_image('mole.png', (100, 100))
MOLE_IMAGE_DOWN = load_image('hit_mole.png', (100, 100))
HAMMER_IMAGE = load_image('hammer.png', (80, 80))

# --- CÁC HÀM LƯU DỮ LIỆU EXCEL (ĐÃ NÂNG CẤP) ---
ANGLES_XLSX = os.path.join(os.path.dirname(__file__), "game_angles_detailed.xlsx")
ANGLES_SUMMARY_XLSX = os.path.join(os.path.dirname(__file__), "game_angles_summary.xlsx")
# (MỚI) Các danh sách này phải khớp với hand_control.py
FINGERS_LIST = ["thumb", "index", "middle", "ring", "pinky"]
BONE_NAMES_LIST = ['index_mcp', 'index_pip', 'middle_mcp', 'middle_pip', 'ring_mcp', 'pinky_mcp']

def ensure_angles_xlsx():
    """(MỚI) Tạo file excel chi tiết với tất cả các cột"""
    if not OPENPYXL or os.path.exists(ANGLES_XLSX):
        return
    wb = Workbook()
    ws = wb.active
    header = ["timestamp", "is_outlier", "is_calibrated"]
    # Thêm cột góc
    for f in FINGERS_LIST:
        header.append(f"{f}_angle")
    # Thêm cột độ dài
    for b in BONE_NAMES_LIST:
        header.append(f"{b}_len")
    # Thêm cột tỷ lệ
    for b in BONE_NAMES_LIST:
        header.append(f"{b}_ratio")
    
    ws.append(header)
    wb.save(ANGLES_XLSX)

def save_angles_xlsx(rehab_data):
    """(MỚI) Lưu 1 dòng dữ liệu chi tiết từ rehab_data"""
    if not OPENPYXL:
        return
    ensure_angles_xlsx()
    wb = load_workbook(ANGLES_XLSX)
    ws = wb.active
    ts = datetime.now().isoformat()
    
    angles = rehab_data.get("angles", {})
    lengths = rehab_data.get("bone_lengths", {})
    ratios = rehab_data.get("bone_ratios", {})
    
    row = [
        ts, 
        rehab_data.get("is_outlier", False), 
        rehab_data.get("is_calibrated", False)
    ]
    for f in FINGERS_LIST:
        row.append(angles.get(f, 0))
    for b in BONE_NAMES_LIST:
        row.append(lengths.get(b, 0))
    for b in BONE_NAMES_LIST:
        row.append(ratios.get(b, 0))
    
    ws.append(row)
    wb.save(ANGLES_XLSX)

def ensure_angles_summary_xlsx():
    """(MỚI) Tạo file tóm tắt (chỉ tóm tắt góc)"""
    if not OPENPYXL or os.path.exists(ANGLES_SUMMARY_XLSX):
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    header = ["timestamp", "player", "round", "frames_recorded"]
    for f in FINGERS_LIST:
        header += [f"{f}_avg", f"{f}_max", f"{f}_min"]
    header += ["outlier_count", "outlier_percentage"]
    ws.append(header)
    wb.save(ANGLES_SUMMARY_XLSX)

def save_angles_summary_xlsx(player, round_no, stats):
    """(MỚI) Lưu tóm tắt góc của 5 ngón"""
    if not OPENPYXL:
        return
    ensure_angles_summary_xlsx()
    wb = load_workbook(ANGLES_SUMMARY_XLSX)
    ws = wb.active
    ts = datetime.now().isoformat()
    
    frames_count = 0
    if 'index' in stats:
        frames_count = stats['index'].get("count", 0)
    
    row = [ts, player, round_no, frames_count]
    
    for f in FINGERS_LIST:
        s = stats.get(f, {"count": 0, "sum": 0.0, "max": 0.0, "min": 999.0})
        cnt = s.get("count", 0)
        avg = (s.get("sum", 0.0) / cnt) if cnt > 0 else 0.0
        mx = s.get("max", 0.0)
        mn = s.get("min", 999.0) if cnt > 0 else 0.0
        row += [round(avg, 1), round(mx, 1), round(mn, 1)]

    outlier_cnt = stats.get("outlier_count", 0)
    outlier_pct = (outlier_cnt / frames_count * 100) if frames_count > 0 else 0.0
    row += [outlier_cnt, round(outlier_pct, 1)]
    
    ws.append(row)
    wb.save(ANGLES_SUMMARY_XLSX)


# --- CLASS MOLE (Giữ nguyên) ---
class Mole(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image_up = MOLE_IMAGE_UP
        self.image_down_hit = MOLE_IMAGE_DOWN
        
        self.hole_image = HOLE_IMAGE
        self.image = self.hole_image
        self.rect = self.hole_image.get_rect(topleft=(x, y))
        self.image = self.image.get_rect(topleft=(x, y))
        self.is_up = False
        self.hit = False
        self.time_up = 0
        self.up_duration = random.randint(MOLE_UP_MIN_MS, MOLE_UP_MAX_MS)
        self.hit_display_time = 300
        self.time_hit = 0

    def show(self):
        if not self.is_up:
            self.is_up = True
            self.hit = False
            self.time_up = pygame.time.get_ticks()
            self.up_duration = random.randint(MOLE_UP_MIN_MS, MOLE_UP_MAX_MS)
            self.image = self.image_up

    def update(self):
        now = pygame.time.get_ticks()
        if self.is_up:
            if self.hit:
                if now - self.time_hit > self.hit_display_time:
                    self.is_up = False
                    self.image = self.hole_image
            elif now - self.time_up > self.up_duration:
                self.is_up = False
                self.image = self.hole_image

    def was_hit(self):
        global score, hit_count
        if self.is_up and not self.hit:
            self.hit = True
            self.image = self.image_down_hit
            self.time_hit = pygame.time.get_ticks()
            score += 10
            hit_count += 1
            return True
        return False

# --- HÀM LƯU LỊCH SỬ (Giữ nguyên) ---
def save_score_to_excel(player_name, score, hit_count, accuracy, filename="game_history.xlsx"):
    if not OPENPYXL: return
    if not os.path.exists(filename):
        wb = Workbook(); ws = wb.active; ws.title = "LichSu"
        ws.append(["Thời gian", "Tên người chơi", "Điểm", "Số lần trúng", "Tỉ lệ phản ứng (%)"])
        wb.save(filename)
    wb = load_workbook(filename); ws = wb.active
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.append([now, player_name, score, hit_count, round(accuracy, 1)])
    wb.save(filename); print(f"✅ Đã lưu kết quả của {player_name} vào {filename}")

# --- HÀM VẼ NÚT (Giữ nguyên) ---
def draw_button(surface, rect, text, font, bg_color, text_color):
    pygame.draw.rect(surface, bg_color, rect, border_radius=10)
    label = font.render(text, True, text_color)
    surface.blit(label, (rect.x + (rect.width - label.get_width()) // 2,
                         rect.y + (rect.height - label.get_height()) // 2))

# --- HÀM NHẬP TÊN + SỐ LẦN CHƠI (Giữ nguyên) ---
def get_player_info():
    pygame.mouse.set_visible(True); pygame.key.start_text_input()
    player_name = ""; num_games = ""; stage = "name"; input_active = True
    while input_active:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.key.stop_text_input(); pygame.quit(); sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    if stage == "name" and player_name.strip(): stage = "num"
                    elif stage == "num" and num_games.strip().isdigit(): input_active = False
                elif event.key == pygame.K_BACKSPACE:
                    if stage == "name": player_name = player_name[:-1]
                    else: num_games = num_games[:-1]
                elif event.key == pygame.K_ESCAPE:
                    pygame.key.stop_text_input(); pygame.quit(); sys.exit()
                else:
                    if stage == "name" and len(player_name) < 15: player_name += event.unicode
                    elif stage == "num" and event.unicode.isdigit() and len(num_games) < 2: num_games += event.unicode
            elif event.type == pygame.MOUSEBUTTONDOWN:
                start_button = pygame.Rect(SCREEN_WIDTH // 2 - 100, 400, 200, 60)
                if start_button.collidepoint(event.pos):
                    if stage == "name" and player_name.strip(): stage = "num"
                    elif stage == "num" and num_games.strip().isdigit(): input_active = False
        screen.blit(BACKGROUND_IMAGE, (0, 0))
        title = "NHAP TEN NGUOI CHOI:" if stage == "name" else "NHAP SO LAN CHOI:"
        current = player_name if stage == "name" else num_games
        text = font.render(title, True, WHITE)
        screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, 180))
        name_text = small_font.render(current + "|", True, GREEN)
        screen.blit(name_text, (SCREEN_WIDTH // 2 - name_text.get_width() // 2, 300))
        start_button = pygame.Rect(SCREEN_WIDTH // 2 - 100, 400, 200, 60)
        draw_button(screen, start_button, "TIEP TUC", small_font, GREEN, WHITE)
        pygame.display.flip(); clock.tick(30)
    pygame.key.stop_text_input(); pygame.mouse.set_visible(False)
    return player_name, int(num_games)
# --- (MỚI) HÀM MÀN HÌNH HIỆU CHỈNH TỰ ĐỘNG ---
def show_calibration_screen(hand_controller):
    calibrated = False
    
    # (MỚI) Biến đếm ngược để đảm bảo tay ổn định
    countdown_start_time = None
    countdown_duration_sec = 3 # Thời gian giữ yên (giây)

    while not calibrated:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                hand_controller.stop_detection()
                pygame.quit(); sys.exit()

        # Lấy dữ liệu camera
        cam_frame, rehab_data, hand_landmarks = hand_controller.get_frame_data()
        if cam_frame is None:
            # Tạo khung hình đen nếu camera chưa sẵn sàng
            cam_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Vẽ lên màn hình Pygame
        screen.blit(BACKGROUND_IMAGE, (0, 0))
        
        # Vẽ khung camera lớn ở giữa
        cam_h, cam_w = 480, 640
        try:
            cam_frame_resized = cv2.resize(cam_frame, (cam_w, cam_h))
            cam_frame_rgb = cv2.cvtColor(cam_frame_resized, cv2.COLOR_BGR2RGB)
            cam_surface = pygame.surfarray.make_surface(cam_frame_rgb.swapaxes(0, 1))
            screen.blit(cam_surface, (SCREEN_WIDTH // 2 - cam_w // 2, SCREEN_HEIGHT // 2 - cam_h // 2 - 50))
        except Exception as e:
            print(f"Lỗi vẽ camera: {e}")

        # (MỚI) Logic đếm ngược
        current_time_ticks = pygame.time.get_ticks()

        if not hand_landmarks:
            # 1. Nếu không thấy tay
            text = small_font.render("Dua tay vao khung hinh...", True, YELLOW)
            countdown_start_time = None # Reset bộ đếm
        else:
            # 2. Nếu thấy tay
            if countdown_start_time is None:
                # 2a. Mới thấy tay, bắt đầu đếm
                countdown_start_time = current_time_ticks
                text = small_font.render("Da thay tay! XOE THANG va GIU YEN...", True, WHITE)
            else:
                # 2b. Đang đếm ngược
                elapsed_sec = (current_time_ticks - countdown_start_time) / 1000.0
                time_left = countdown_duration_sec - int(elapsed_sec)
                
                if time_left > 0:
                    text = small_font.render(f"Giu yen tay... {time_left}", True, WHITE)
                else:
                    # 2c. Đếm xong, tiến hành hiệu chỉnh
                    text = small_font.render("Dang hieu chinh...", True, GREEN)
                    pygame.display.flip() # Cập nhật màn hình
                    
                    if hand_controller.calibrate(hand_landmarks):
                        calibrated = True # Hiệu chỉnh thành công!
                    else:
                        # Hiệu chỉnh thất bại (ví dụ: tay co lại)
                        text = small_font.render("Loi! Thu lai...", True, RED)
                        countdown_start_time = None # Reset để thử lại
                        pygame.display.flip()
                        pygame.time.wait(500) # Chờ 0.5s trước khi thử lại

        # Vẽ chữ hướng dẫn
        screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, 100))
        pygame.display.flip()
        clock.tick(FPS)
    
    # Đã hiệu chỉnh xong, hiển thị thông báo
    screen.blit(BACKGROUND_IMAGE, (0, 0))
    text = font.render("DA SAN SANG!", True, GREEN)
    screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, 350))
    pygame.display.flip()
    pygame.time.wait(2000) # Chờ 2 giây trước khi vào game

# --- KHỞI TẠO GAME ---
base_x, base_y = 220, 250
x_spacing, y_spacing = 170, 120
mole_positions = [(base_x + i * x_spacing, base_y + j * y_spacing) for j in range(3) for i in range(3)]
moles = [Mole(x, y) for x, y in mole_positions]

hand_controller = HandController()
hand_controller.start_detection()

gesture_cooldown = 0.3 
last_gesture_time = 0.0

# --- VÒNG LẶP TOÀN GAME ---
while True:
    player_name, total_rounds = get_player_info()
    
    # (MỚI) CHẠY HIỆU CHỈNH TỰ ĐỘNG 1 LẦN
    show_calibration_screen(hand_controller)
    
    round_count = 0
    while round_count < total_rounds:
        score = 0; hit_count = 0; total_moles_shown = 0
        game_time = 30; game_over = False
        start_time = pygame.time.get_ticks()

        # Khởi tạo thống kê góc (cho 5 ngón)
        angle_stats = {f: {"count": 0, "sum": 0.0, "max": 0.0, "min": 999.0} for f in FINGERS_LIST}
        angle_stats["outlier_count"] = 0 

        running = True
        while running:
            # --- XỬ LÝ SỰ KIỆN ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    hand_controller.stop_detection()
                    pygame.quit(); sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN and game_over:
                    if play_again_rect.collidepoint(pygame.mouse.get_pos()):
                        running = False
            
            # --- LẤY DỮ LIỆU TAY (ĐÃ NÂNG CẤP) ---
            cam_frame, rehab_data, hand_landmarks = hand_controller.get_frame_data()
            
            # --- CẬP NHẬT THỐNG KÊ (ĐÃ NÂNG CẤP) ---
            if rehab_data['is_calibrated']:
                if rehab_data['is_outlier']: 
                    angle_stats["outlier_count"] += 1
                
                # Lưu file excel chi tiết MỖI FRAME (nếu đã hiệu chỉnh)
                save_angles_xlsx(rehab_data)
                
                for f, val in rehab_data.get('angles', {}).items():
                    if f in angle_stats: 
                        s = angle_stats[f]
                        s["count"] += 1
                        s["sum"] += val
                        if val > s["max"]: s["max"] = val
                        if val < s["min"]: s["min"] = val

            # --- LOGIC GAME CHÍNH ---
            if not game_over:
                elapsed = (pygame.time.get_ticks() - start_time) // 1000
                if elapsed >= game_time:
                    game_over = True
                    acc = (hit_count / total_moles_shown * 100) if total_moles_shown > 0 else 0
                    save_score_to_excel(player_name, score, hit_count, acc)
                    save_angles_summary_xlsx(player_name, round_count + 1, angle_stats)

                for mole in moles:
                    mole.update()

                up_count = sum(1 for m in moles if m.is_up)
                if up_count < MAX_SIMULTANEOUS_MOLES and random.randint(1, SPAWN_DENOM) == 1:
                    available = [m for m in moles if not m.is_up]
                    if available:
                        random.choice(available).show()
                        total_moles_shown += 1
                
                # --- ĐỊNH NGHĨA "CÚ ĐẬP" (SỬ DỤNG GÓC TRUNG BÌNH 3 NGÓN) ---
                hand_position = rehab_data['hand_pos']
                gesture = False
                now = time.time()
                angles_dict = rehab_data.get('angles', {})
                avg_flex_angle = (angles_dict.get('index', 0) + angles_dict.get('middle', 0) + angles_dict.get('ring', 0)) / 3.0
                
                # Ngưỡng đập là 50 độ
                if rehab_data['is_calibrated'] and not rehab_data['is_outlier'] and avg_flex_angle > 50 and (now - last_gesture_time > gesture_cooldown):
                    gesture = True
                    last_gesture_time = now

                if hand_position and gesture:
                    for mole in moles:
                        if mole.rect.collidepoint(hand_position):
                            mole.was_hit()

            # --- VẼ LÊN MÀN HÌNH ---
            screen.blit(BACKGROUND_IMAGE, (0, 0))
            for mole in moles:
                screen.blit(mole.hole_image, mole.rect)
            for mole in moles:
                if mole.is_up:
                    screen.blit(mole.image, mole.rect)
            
            score_text = small_font.render(f"Score: {score}", True, BLACK)
            time_text = small_font.render(f"Time: {max(0, game_time - (pygame.time.get_ticks() - start_time)//1000)}s", True, BLACK)
            screen.blit(score_text, (10, 10))
            screen.blit(time_text, (SCREEN_WIDTH - time_text.get_width() - 10, 10))

            if hand_position:
                screen.blit(HAMMER_IMAGE, (hand_position[0]-30, hand_position[1]-30))

            # --- HIỂN THỊ TRẠNG THÁI HIỆU CHỈNH & GÓC ---
            status_text = "DANG CHO TAY..."
            status_color = RED
            if rehab_data['is_calibrated']:
                status_text = "DANG DO..."
                status_color = GREEN
                if rehab_data['is_outlier']:
                    status_text = "TIN HIEU YEU (NHIEU)"
                    status_color = YELLOW
            
            angles_dict = rehab_data.get('angles', {})
            index_angle_display = angles_dict.get('index', 0.0)
            avg_angle_display = np.mean(list(angles_dict.values())) if angles_dict else 0.0
            
            angle_text_1 = f"Goc (Tro): {index_angle_display:.1f}"
            angle_text_2 = f"TBinh (5 ng.): {avg_angle_display:.1f}"
            
            cv2.putText(cam_frame, status_text, (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 1, cv2.LINE_AA)
            cv2.putText(cam_frame, angle_text_1, (5, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, CYAN, 1, cv2.LINE_AA)
            cv2.putText(cam_frame, angle_text_2, (5, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, CYAN, 1, cv2.LINE_AA)

            # Vẽ màn hình Game Over
            if game_over:
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
                play_again_rect = pygame.Rect(SCREEN_WIDTH//2 - 100, 600, 200, 60)
                draw_button(screen, play_again_rect, "LUOT TIEP", small_font, GREEN, WHITE)

            # Vẽ khung camera
            if cam_frame is not None:
                cam_h, cam_w = 150, 180
                cam_frame_resized = cv2.resize(cam_frame, (cam_w, cam_h))
                cam_frame_rgb = cv2.cvtColor(cam_frame_resized, cv2.COLOR_BGR2RGB)
                cam_surface = pygame.surfarray.make_surface(cam_frame_rgb.swapaxes(0, 1))
                screen.blit(cam_surface, (10, SCREEN_HEIGHT - cam_h - 10))

            pygame.display.flip()
            clock.tick(FPS)

        round_count += 1

    # --- Hết số lần chơi ---
    screen.fill(BLACK)
    msg = font.render("DA HOAN THANH!", True, RED)
    msg2 = small_font.render("An phim bat ky de choi lai", True, WHITE)
    screen.blit(msg, (SCREEN_WIDTH//2 - msg.get_width()//2, 300))
    screen.blit(msg2, (SCREEN_WIDTH//2 - msg2.get_width()//2, 400))
    pygame.display.flip()

    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                hand_controller.stop_detection(); pygame.quit(); sys.exit()
            elif event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
                waiting = False