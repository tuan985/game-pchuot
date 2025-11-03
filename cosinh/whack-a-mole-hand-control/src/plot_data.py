import pandas as pd
import matplotlib.pyplot as plt
import os

# (MỚI) Lấy đường dẫn tuyệt đối của thư mục chứa file script này (thư mục 'src')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- CÀI ĐẶT ---
# (SỬA) Nối đường dẫn tuyệt đối để Python luôn tìm đúng chỗ
FILE_TO_ANALYZE = os.path.join(BASE_DIR, 'game_angles_detailed.xlsx')
CHART_OUTPUT_FILE = os.path.join(BASE_DIR, 'hand_movement_chart.png')
FINGERS_LIST = ["thumb", "index", "middle", "ring", "pinky"]
# -----------------

def plot_hand_movement():
    # --- (ĐÃ SỬA LỖI FONT CHỮ) ---
    print(f"Dang doc file du lieu '{os.path.basename(FILE_TO_ANALYZE)}'...")
    
    # 1. Kiểm tra file (Đã dùng đường dẫn tuyệt đối)
    if not os.path.exists(FILE_TO_ANALYZE):
        print(f"Loi: Khong tim thay file '{os.path.basename(FILE_TO_ANALYZE)}'.")
        # Thêm dòng này để bạn biết nó đang tìm ở đâu:
        print(f"File duoc tim tai: {FILE_TO_ANALYZE}") 
        print("Hay chay game 'app.py' it nhat mot lan de tao file du lieu.")
        return

    # 2. Đọc dữ liệu bằng Pandas
    try:
        df = pd.read_excel(FILE_TO_ANALYZE)
    except Exception as e:
        print(f"Loi khi doc file Excel: {e}")
        return

    if df.empty:
        print("Loi: File du lieu rong.")
        return

    # 3. Xử lý dữ liệu
    try:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    except Exception as e:
        print(f"Loi dinh dang cot timestamp: {e}")
        return
        
    df_clean = df[df['is_outlier'] == False].copy()

    if df_clean.empty:
        print("Khong co du lieu hop le (tat ca deu bi nhieu). Khong the ve bieu do.")
        return
        
    start_time = df_clean['timestamp'].iloc[0]
    df_clean['time_elapsed_sec'] = (df_clean['timestamp'] - start_time).dt.total_seconds()

    # 4. Vẽ biểu đồ
    print("Dang tao bieu do...")
    plt.figure(figsize=(15, 7))

    for finger in FINGERS_LIST:
        col_name = f'{finger}_angle'
        if col_name in df_clean.columns:
            plt.plot(df_clean['time_elapsed_sec'], df_clean[col_name], label=finger.capitalize())

    # 5. Tùy chỉnh biểu đồ
    plt.xlabel('Thoi gian (giay) trong van choi', fontsize=12)
    plt.ylabel('Goc gap (do)', fontsize=12)
    plt.title('Bieu do Chuyen dong Cac ngon tay (Da loc nhieu)', fontsize=16)
    plt.legend(loc='upper right') 
    plt.grid(True, linestyle='--', alpha=0.6) 
    plt.tight_layout() 

    # 6. Lưu file
    try:
        # (SỬA) Dùng đường dẫn tuyệt đối để lưu
        plt.savefig(CHART_OUTPUT_FILE)
        print(f"Thanh cong! Da luu bieu do vao file: '{CHART_OUTPUT_FILE}'")
    except Exception as e:
        print(f"Loi khi luu bieu do: {e}")

if __name__ == "__main__":
    plot_hand_movement()
