import sys
import time
import threading
import traceback
import cv2
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

print("=== ЗАПУСК ПРОГРАММЫ ===")
print(f"Python версия: {sys.version}")

# Попытка импорта библиотек с проверкой
try:
    from ultralytics import YOLO
    print("Библиотека Ultralytics (YOLO) успешно импортирована.")
except ImportError as e:
    print(f"!!! ОШИБКА ИМПОРТА !!! Не установлена ultralytics. Выполните pip install ultralytics. Детали: {e}")
    input("Нажмите Enter для выхода...")
    sys.exit(1)

# --- Глобальные настройки ---
MODEL_PATH = 'yolov8n.pt'
CONF_THRESHOLD = 0.5

class DogMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Dog Monitor - Diagnostic Mode")
        self.root.geometry("1000x700")
        
        # Флаги управления
        self.is_running = False
        self.camera_index = None
        self.cap = None
        self.latest_frame = None
        self.detections_text = "Система готова к запуску."
        self.yolo_model = None
        self.processing_time = 0

        # --- Интерфейс ---
        # Видео
        self.video_label = tk.Label(root, text="Ожидание видео...", bg="black", fg="white")
        self.video_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Панель управления
        self.panel = ttk.Frame(root)
        self.panel.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        self.btn_start = ttk.Button(self.panel, text="НАЙТИ КАМЕРУ И ЗАПУСТИТЬ", command=self.start_system)
        self.btn_start.pack(fill=tk.X, pady=10)

        self.btn_stop = ttk.Button(self.panel, text="Остановить", command=self.stop_system, state=tk.DISABLED)
        self.btn_stop.pack(fill=tk.X, pady=5)

        self.lbl_status = ttk.Label(self.panel, text="Статус: Ожидание", wraplength=200)
        self.lbl_status.pack(fill=tk.X, pady=10)

        self.txt_log = tk.Text(self.panel, height=20, width=30)
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        
        print("Интерфейс инициализирован.")

    def log_message(self, msg):
        """Вывод сообщений в консоль и в окно программы"""
        print(f"[LOG] {msg}")
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)

    def find_working_camera(self):
        """Перебор индексов для поиска рабочей камеры"""
        self.log_message("Начинаю поиск камеры (0-5)...")
        for idx in range(6):
            try:
                cap = cv2.VideoCapture(idx)
                if cap.isOpened():
                    ret, _ = cap.read()
                    if ret:
                        self.log_message(f"✅ Камера найдена по индексу: {idx}")
                        cap.release()
                        return idx
                    else:
                         cap.release()
            except Exception as e:
                print(f"Ошибка при проверке индекса {idx}: {e}")
        
        self.log_message("❌ РАБОЧАЯ КАМЕРА НЕ НАЙДЕНА!")
        return None

    def load_model_safely(self):
        """Безопасная загрузка модели"""
        self.log_message("Загрузка нейросети YOLOv8n...")
        try:
            self.yolo_model = YOLO(MODEL_PATH)
            # Прогоняем пустой массив для инициализации
            import numpy as np
            dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
            self.yolo_model(dummy_frame, verbose=False)
            self.log_message("✅ Нейросеть загружена и готова.")
            return True
        except Exception as e:
            self.log_message(f"❌ Ошибка загрузки модели: {e}")
            traceback.print_exc()
            return False

    def start_system(self):
        self.btn_start.config(state=tk.DISABLED)
        
        # 1. Поиск камеры
        self.camera_index = self.find_working_camera()
        if self.camera_index is None:
            self.lbl_status.config(text="Ошибка: Камера не найдена")
            self.btn_start.config(state=tk.NORMAL)
            return

        # 2. Загрузка модели (если еще нет)
        if self.yolo_model is None:
            if not self.load_model_safely():
                self.lbl_status.config(text="Ошибка: Сбой модели")
                self.btn_start.config(state=tk.NORMAL)
                return

        # 3. Запуск потоков
        self.is_running = True
        self.cap = cv2.VideoCapture(self.camera_index)
        
        # Запускаем поток обработки YOLO
        threading.Thread(target=self.yolo_thread_loop, daemon=True).start()
        
        # Запускаем обновление UI
        self.btn_stop.config(state=tk.NORMAL)
        self.update_ui_loop()

    def stop_system(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.log_message("Система остановлена пользователем.")

    def yolo_thread_loop(self):
        """Этот код работает параллельно и не тормозит окно"""
        self.log_message("Поток YOLO запущен.")
        while self.is_running and self.cap.isOpened():
            try:
                ret, frame = self.cap.read()
                if not ret:
                    self.log_message("Ошибка чтения кадра!")
                    time.sleep(1)
                    continue

                # Замер времени
                t0 = time.time()
                
                # Детекция
                results = self.yolo_model(frame, verbose=False, conf=CONF_THRESHOLD)
                
                t1 = time.time()
                self.processing_time = (t1 - t0) * 1000

                detections = []
                # Рисование
                for r in results:
                    boxes = r.boxes
                    for box in boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        cls = int(box.cls[0])
                        name = self.yolo_model.names[cls]
                        conf = float(box.conf[0])
                        
                        # Рисуем
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, f"{name} {conf:.2f}", (x1, y1 - 10), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                        
                        detections.append(f"{name}")

                # Сохраняем готовый кадр для UI
                # OpenCV использует BGR, Tkinter любит RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.latest_frame = frame
                
                if detections:
                    self.detections_text = ", ".join(set(detections))
                else:
                    self.detections_text = "Ничего не найдено"
                
                # Небольшая пауза, чтобы не плавить процессор
                # Если обработка быстрая, спим дольше. Если медленная - не спим.
                # time.sleep(0.01) 

            except Exception as e:
                print(f"Ошибка в цикле YOLO: {e}")
                time.sleep(1)

    def update_ui_loop(self):
        """Обновление картинки на экране"""
        if not self.is_running:
            return

        if self.latest_frame is not None:
            # Превращаем массив пикселей в картинку
            img = Image.fromarray(self.latest_frame)
            # Ресайз под окно, чтобы не тормозило
            img = img.resize((800, 600), Image.Resampling.LANCZOS)
            imgtk = ImageTk.PhotoImage(image=img)
            
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
            
            self.lbl_status.config(text=f"YOLO: {self.processing_time:.1f}ms | Вижу: {self.detections_text}")

        # Планируем следующий кадр через 30 мс (около 30 FPS обновления UI)
        self.root.after(30, self.update_ui_loop)

# --- Точка входа ---
if __name__ == "__main__":
    print("Инициализация Tkinter...")
    try:
        root = tk.Tk()
        app = DogMonitorApp(root)
        print("Вход в главный цикл (mainloop)...")
        root.mainloop()
        print("Программа закрыта.")
    except Exception as e:
        print("КРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ:")
        traceback.print_exc()
        input("Нажмите Enter чтобы закрыть...")
