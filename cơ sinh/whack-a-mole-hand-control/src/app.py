import pygame
import random
import sys
import os
import cv2
from hand_control import HandController

def draw_button(surface, rect, text, font, bg_color, text_color):
    pygame.draw.rect(surface, bg_color, rect, border_radius=10)
    label = font.render(text, True, text_color)
    surface.blit(label, (rect.x + (rect.width - label.get_width()) // 2,
                         rect.y + (rect.height - label.get_height()) // 2))

# --- THIẾT LẬP CƠ BẢN ---
pygame.init()

# Kích thước màn hình
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Game Đập Chuột")

fullscreen = False  # <-- Thêm dòng này

# Bộ đếm thời gian
clock = pygame.time.Clock()
FPS = 120

# ẨN CON TRỎ MẶC ĐỊNH
pygame.mouse.set_visible(False)

# Màu sắc
WHITE = (255, 255, 255)
RED = (255, 0, 0)
BLACK = (0, 0, 0)
GREEN = (0, 150, 0) 

# Điểm số và thời gian
score = 0
game_time = 30  # Thời gian chơi (giây)

# Phông chữ
font = pygame.font.Font(None, 74)
small_font = pygame.font.Font(None, 36)

# --- TẢI HÌNH ẢNH ---
def load_image(file_name, size=None):
    path = os.path.join('assets', file_name)
    try:
        image = pygame.image.load(path).convert_alpha()
        if size:
            return pygame.transform.scale(image, size)
        return image
    except pygame.error as e:
        print(f"Không thể tải ảnh: {path}. Lỗi: {e}")
        print(f"Hãy đảm bảo bạn đã tạo thư mục 'assets' và file '{file_name}'!")
        placeholder_size = size if size else (100, 100)
        placeholder = pygame.Surface(placeholder_size)
        placeholder.fill(GREEN)
        return placeholder

# Tải các hình ảnh cần thiết cho Game Đập Chuột
BACKGROUND_IMAGE = load_image('background.png', (SCREEN_WIDTH, SCREEN_HEIGHT))
HOLE_IMAGE = load_image('hole.png', (150, 100))
MOLE_IMAGE_UP = load_image('mole.png', (100, 100))
MOLE_IMAGE_DOWN = load_image('hit_mole.png', (100, 100))
HAMMER_IMAGE = load_image('hammer.png', (80, 80))

# --- CLASS ĐỐI TƯỢNG CHUỘT ---
class Mole(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.image_up = MOLE_IMAGE_UP
        self.image_down_hit = MOLE_IMAGE_DOWN
        self.hole_image = HOLE_IMAGE

        self.image = self.hole_image
        self.rect = self.image.get_rect(topleft=(x, y))
        
        self.is_up = False
        self.hit = False
        self.time_up = 0
        self.up_duration = random.randint(1000, 2500)
        self.hit_display_time = 300 
        self.time_hit = 0

    def show(self):
        if not self.is_up:
            self.is_up = True
            self.hit = False
            self.time_up = pygame.time.get_ticks()
            self.image = self.image_up 
            self.rect = self.image.get_rect(center=(self.rect.centerx, self.rect.centery - 10))

    def update(self):
        current_time = pygame.time.get_ticks()
        
        if self.is_up:
            if self.hit:
                if current_time - self.time_hit > self.hit_display_time:
                    self.is_up = False
                    self.image = self.hole_image
                    self.rect = self.hole_image.get_rect(topleft=self.rect.topleft)
            elif current_time - self.time_up > self.up_duration: 
                self.is_up = False
                self.image = self.hole_image
                self.rect = self.hole_image.get_rect(topleft=self.rect.topleft)

    def was_hit(self):
        if self.is_up and not self.hit:
            self.hit = True
            self.image = self.image_down_hit
            self.time_hit = pygame.time.get_ticks()
            global score
            score += 10
            return True
        return False

# --- KHỞI TẠO GAME ---
hole_width, hole_height = HOLE_IMAGE.get_size()

base_x = 220
base_y = 250
x_spacing = 170
y_spacing = 120

mole_center_positions = [
    (base_x, base_y), (base_x + x_spacing, base_y), (base_x + 2 * x_spacing, base_y),
    (base_x, base_y + y_spacing), (base_x + x_spacing, base_y + y_spacing), (base_x + 2 * x_spacing, base_y + y_spacing),
    (base_x, base_y + 2 * y_spacing), (base_x + x_spacing, base_y + 2 * y_spacing), (base_x + 2 * x_spacing, base_y + 2 * y_spacing),
]

moles = []
for cx, cy in mole_center_positions:
    hole_x = cx - hole_width // 2
    hole_y = cy - hole_height // 2
    moles.append(Mole(hole_x, hole_y))

# Biến điều khiển game
running = True
game_over = False
start_time = pygame.time.get_ticks()

# Khởi tạo HandController
hand_controller = HandController()
cam_on = True
hand_controller.start_detection()

# --- VÒNG LẶP GAME CHÍNH ---
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_c:
                cam_on = not cam_on
                if cam_on:
                    hand_controller.start_detection()
                else:
                    hand_controller.stop_detection()
            if event.key == pygame.K_F11:
                fullscreen = not fullscreen
                if fullscreen:
                    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
                else:
                    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        if event.type == pygame.MOUSEBUTTONDOWN and game_over:
            mouse_pos = pygame.mouse.get_pos()
            if play_again_rect.collidepoint(mouse_pos):
                # Reset game state
                score = 0
                game_over = False
                start_time = pygame.time.get_ticks()
                for mole in moles:
                    mole.is_up = False
                    mole.hit = False
                    mole.image = mole.hole_image

    # Cập nhật vị trí tay và kiểm tra động tác gõ
    if cam_on:
        hand_position, gesture, cam_frame = hand_controller.get_hand_position()

        if not game_over:
            elapsed_time = (pygame.time.get_ticks() - start_time) // 1000
            time_left = game_time - elapsed_time
            
            if time_left <= 0:
                game_over = True
            
            for mole in moles:
                mole.update()
            
            # Logic cho chuột xuất hiện ngẫu nhiên
            if random.randint(1, 60) == 1: 
                available_moles = [m for m in moles if not m.is_up]
                if available_moles:
                    random_mole = random.choice(available_moles)
                    random_mole.show()

            # Kiểm tra nếu tay ở vị trí nào đó và có động tác gõ để đánh chuột
            if hand_position and gesture:
                for mole in moles:
                    if mole.rect.collidepoint(hand_position):
                        mole.was_hit()
    else:
        hand_position, gesture, cam_frame = None, False, None
        if not game_over:
            elapsed_time = (pygame.time.get_ticks() - start_time) // 1000
            time_left = game_time - elapsed_time
            
            if time_left <= 0:
                game_over = True
            
            for mole in moles:
                mole.update()
            
            # Logic cho chuột xuất hiện ngẫu nhiên
            if random.randint(1, 60) == 1: 
                available_moles = [m for m in moles if not m.is_up]
                if available_moles:
                    random_mole = random.choice(available_moles)
                    random_mole.show()

            # Kiểm tra nếu tay ở vị trí nào đó và có động tác gõ để đánh chuột
            if hand_position and gesture:
                for mole in moles:
                    if mole.rect.collidepoint(hand_position):
                        mole.was_hit()

    # --- Vẽ lên màn hình ---
    screen.blit(BACKGROUND_IMAGE, (0, 0))
    
    for mole in moles:
        screen.blit(mole.hole_image, mole.rect)

    for mole in moles:
        if mole.is_up:
             screen.blit(mole.image, mole.rect)
    
    score_text = small_font.render(f"Score: {score}", True, BLACK)
    screen.blit(score_text, (10, 10))
    
    time_text = small_font.render(f"Time: {max(0, time_left)}s", True, BLACK)
    screen.blit(time_text, (SCREEN_WIDTH - time_text.get_width() - 10, 10))
    
    # VẼ HÌNH ẢNH CÁI BÚA THEO TỌA ĐỘ TAY
    if hand_position:
        hammer_offset_x = 20
        hammer_offset_y = 20
        screen.blit(HAMMER_IMAGE, (hand_position[0] - hammer_offset_x, hand_position[1] - hammer_offset_y))

    if game_over:
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))
        
        game_over_text = font.render("GAME OVER", True, RED)
        final_score_text = small_font.render(f"Final Score: {score}", True, WHITE)
        
        screen.blit(game_over_text, (SCREEN_WIDTH // 2 - game_over_text.get_width() // 2, SCREEN_HEIGHT // 3))
        screen.blit(final_score_text, (SCREEN_WIDTH // 2 - final_score_text.get_width() // 2, SCREEN_HEIGHT // 3 + 100))
        
        # Vẽ nút chơi lại
        button_w, button_h = 200, 60
        button_x = SCREEN_WIDTH // 2 - button_w // 2
        button_y = SCREEN_HEIGHT // 3 + 200
        play_again_rect = pygame.Rect(button_x, button_y, button_w, button_h)
        draw_button(screen, play_again_rect, "CHOI LAI", small_font, GREEN, WHITE)
    
    # Hiển thị camera ở góc phải dưới
    if cam_frame is not None:
        cam_h, cam_w = 150, 180  # Kích thước khung camera nhỏ
        cam_frame = cv2.resize(cam_frame, (cam_w, cam_h))
        cam_frame = cv2.cvtColor(cam_frame, cv2.COLOR_BGR2RGB)
        cam_surface = pygame.surfarray.make_surface(cam_frame.swapaxes(0, 1))
        screen.blit(cam_surface, (SCREEN_WIDTH - cam_w - 10, SCREEN_HEIGHT - cam_h - 10))

    if game_over:
        pygame.mouse.set_visible(True)
    else:
        pygame.mouse.set_visible(False)

    pygame.display.flip()
    clock.tick(FPS)

# Thoát Pygame
hand_controller.stop_detection()
pygame.quit()
sys.exit()