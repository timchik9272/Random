import cv2
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from ultralytics import YOLO
import threading
import time
import math
import numpy as np

# --- НАСТРОЙКИ ---
MODEL_PATH = 'yolov8n.pt'
CONF_THRESHOLD = 0.45   # Порог уверенности
MOVEMENT_THRESHOLD = 20 # Сколько пикселей считается движением за интервал
MOVEMENT_INTERVAL = 1.0 # Интервал времени для проверки движения (секунды)
YOLO_IMG_SIZE = 640     # Размер для обработки нейросетью (меньше = быстрее на CPU)

class SmartDogMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Dog Activity Monitor (CPU Optimized)")
        self.root.geometry("1100x700")

        # --- Глобальные переменные состояния ---
        self.cap = None
        self.is_camera_running = False
        self.is_ai_running = False
        self.setup_mode = False
        
        # Переменные для видео и ИИ
        self.latest_frame_cv = None # Последний "сырой" кадр с камеры
        self.ai_results = None      # Последние результаты от нейросети (бокс, текст)
        self.lock = threading.Lock() # Для безопасного обмена данными между потоками

        # Переменные для логики действий
        self.bed_zone = None # (x1, y1, x2, y2) красной зоны
        self.last_position = None # (cx, cy) центра собаки
        self.last_position_time = 0
        self.dog_status_text = "Ожидание..."

        # Переменные для рисования мышкой
        self.draw_start_x = None
        self.draw_start_y = None
        self.temp_bed_rect = None

        # --- Инициализация модели ---
        print("Загрузка модели YOLOv8n (только для собак)...")
        try:
            self.model = YOLO(MODEL_PATH)
            # Прогрев модели
            self.model(np.zeros((640, 640, 3), dtype=np.uint8), verbose=False, classes=[16])
            print("Модель готова.")
        except Exception as e:
            print(f"Ошибка загрузки модели: {e}")
            root.destroy()
            return

        self._setup_ui()

    def _setup_ui(self):
        # Фрейм для видео (слева)
        video_frame = tk.Frame(self.root, width=800, height=600, bg="black")
        video_frame.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.BOTH, expand=True)
        # Используем Canvas для возможности рисования мышкой
        self.canvas = tk.Canvas(video_frame, bg="black", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Привязка событий мыши к холсту
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        # Панель управления (справа)
        control_panel = tk.Frame(self.root, width=250)
        control_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        ttk.Label(control_panel, text="ПАНЕЛЬ УПРАВЛЕНИЯ", font=("Arial", 12, "bold")).pack(pady=10)

        self.btn_cam = ttk.Button(control_panel, text="1. Включить камеру", command=self.start_camera)
        self.btn_cam.pack(fill=tk.X, pady=5)

        self.btn_setup = ttk.Button(control_panel, text="2. Задать зону лежанки (мышкой)", command=self.enter_setup_mode, state=tk.DISABLED)
        self.btn_setup.pack(fill=tk.X, pady=5)

        self.btn_start_ai = ttk.Button(control_panel, text="3. ЗАПУСК МОНИТОРИНГА", command=self.start_monitoring, state=tk.DISABLED)
        self.btn_start_ai.pack(fill=tk.X, pady=10)
        
        self.btn_stop_all = ttk.Button(control_panel, text="ОСТАНОВИТЬ ВСЁ", command=self.stop_all, state=tk.DISABLED)
        self.btn_stop_all.pack(fill=tk.X, pady=(20, 5))

        self.status_label = ttk.Label(control_panel, text="Статус: Готов к запуску", wraplength=230, font=("Arial", 10))
        self.status_label.pack(pady=20, fill=tk.X)

        self.fps_label = ttk.Label(control_panel, text="FPS ИИ: 0")
        self.fps_label.pack(side=tk.BOTTOM, pady=10)

    # --- Функции рисования мышкой ---
    def on_mouse_down(self, event):
        if self.setup_mode:
            self.draw_start_x = event.x
            self.draw_start_y = event.y
            if self.temp_bed_rect:
                self.canvas.delete(self.temp_bed_rect)

    def on_mouse_drag(self, event):
        if self.setup_mode and self.draw_start_x:
            if self.temp_bed_rect:
                self.canvas.delete(self.temp_bed_rect)
            self.temp_bed_rect = self.canvas.create_rectangle(
                self.draw_start_x, self.draw_start_y, event.x, event.y,
                outline="red", width=2, dash=(4, 4)
            )

    def on_mouse_up(self, event):
        if self.setup_mode and self.draw_start_x:
            x1 = min(self.draw_start_x, event.x)
            y1 = min(self.draw_start_y, event.y)
            x2 = max(self.draw_start_x, event.x)
            y2 = max(self.draw_start_y, event.y)
            # Сохраняем координаты зоны (с учетом масштабирования, если окно меняло размер)
            # Для простоты привязываемся к текущему размеру канваса
            self.bed_zone = (x1, y1, x2, y2)
            self.status_label.config(text="Зона лежанки задана. Можно запускать мониторинг.")
            self.btn_start_ai.config(state=tk.NORMAL)
            self.draw_start_x = None

    # --- Управление состояниями ---
    def start_camera(self):
        if not self.is_camera_running:
            try:
                # Пробуем открыть камеру (индекс 0, если не выйдет - попробуйте 1)
                self.cap = cv2.VideoCapture(0) 
                if not self.cap.isOpened():
                     self.cap = cv2.VideoCapture(1)
                
                if not self.cap.isOpened():
                     raise Exception("Не удалось открыть камеру")

                self.is_camera_running = True
                self.btn_cam.config(state=tk.DISABLED)
                self.btn_setup.config(state=tk.NORMAL)
                self.btn_stop_all.config(state=tk.NORMAL)
                self.status_label.config(text="Камера работает. Задайте лежанку.")
                
                # Запускаем поток захвата видео
                threading.Thread(target=self.camera_thread, daemon=True).start()
                # Запускаем цикл обновления UI
                self.update_ui_loop()
            except Exception as e:
                self.status_label.config(text=f"Ошибка камеры: {e}")

    def enter_setup_mode(self):
        self.setup_mode = True
        self.canvas.config(cursor="crosshair")
        self.status_label.config(text="РЕЖИМ НАСТРОЙКИ: Нарисуйте прямоугольник лежанки на видео.")

    def start_monitoring(self):
        if self.bed_zone is None:
             self.status_label.config(text="ОШИБКА: Сначала задайте зону лежанки!")
             return
        self.setup_mode = False
        self.is_ai_running = True
        self.canvas.config(cursor="arrow")
        self.btn_setup.config(state=tk.DISABLED)
        self.btn_start_ai.config(state=tk.DISABLED)
        self.status_label.config(text="МОНИТОРИНГ ЗАПУЩЕН. Идет поиск собаки...")
        
        # Запускаем поток ИИ
        threading.Thread(target=self.ai_processing_thread, daemon=True).start()

    def stop_all(self):
        self.is_camera_running = False
        self.is_ai_running = False
        self.setup_mode = False
        if self.cap:
            self.cap.release()
        self.root.quit()

    # --- Потоки ---
    def camera_thread(self):
        """Поток 1: Только захват кадров с камеры (максимально быстро)"""
        while self.is_camera_running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # Зеркалим для удобства (опционально)
                frame = cv2.flip(frame, 1) 
                with self.lock:
                    self.latest_frame_cv = frame
            else:
                time.sleep(0.1)

    def ai_processing_thread(self):
        """Поток 2: Обработка ИИ и логика (на пределе возможностей CPU)"""
        frame_count = 0
        start_time = time.time()

        while self.is_ai_running:
            frame_to_process = None
            with self.lock:
                if self.latest_frame_cv is not None:
                    frame_to_process = self.latest_frame_cv.copy()
            
            if frame_to_process is None:
                time.sleep(0.05)
                continue

            # 1. ИНФЕРЕНС (Самая тяжелая часть)
            # classes=[16] заставляет искать ТОЛЬКО собак.
            # imgsz=YOLO_IMG_SIZE уменьшает размер для ускорения.
            results = self.model(frame_to_process, verbose=False, conf=CONF_THRESHOLD, classes=[16], imgsz=YOLO_IMG_SIZE)

            current_dog_box = None
            current_dog_center = None
            
            # 2. Поиск лучшего кандидата (если несколько собак, берем самую уверенную)
            best_conf = 0
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    conf = float(box.conf[0])
                    if conf > best_conf:
                        best_conf = conf
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        current_dog_box = (x1, y1, x2, y2)
                        cx = (x1 + x2) // 2
                        cy = (y1 + y2) // 2
                        current_dog_center = (cx, cy)

            # 3. ЛОГИКА ДЕЙСТВИЙ
            status = "Не видно"
            if current_dog_center:
                now = time.time()
                
                # Проверка движения (сравниваем с позицией X секунд назад)
                is_moving = False
                if self.last_position and (now - self.last_position_time > MOVEMENT_INTERVAL):
                    dist = math.sqrt((current_dog_center[0] - self.last_position[0])**2 + 
                                     (current_dog_center[1] - self.last_position[1])**2)
                    if dist > MOVEMENT_THRESHOLD:
                        is_moving = True
                    
                    # Обновляем "старую" позицию
                    self.last_position = current_dog_center
                    self.last_position_time = now
                elif self.last_position is None:
                    self.last_position = current_dog_center
                    self.last_position_time = now
                    status = "Анализ..."

                # Проверка зоны лежанки (нужно масштабировать координаты канваса к координатам кадра)
                # Для упрощения предположим, что размер видео = размеру канваса при настройке.
                # В идеале нужно учитывать scale factor, если окно меняет размер.
                in_bed = False
                if self.bed_zone:
                    bx1, by1, bx2, by2 = self.bed_zone
                    # Простейшая проверка попадания центра в прямоугольник
                    # ВАЖНО: Это работает точно, только если размер окна не менялся после настройки.
                    h, w, _ = frame_to_process.shape
                    canv_w = self.canvas.winfo_width()
                    canv_h = self.canvas.winfo_height()
                    if canv_w > 0 and canv_h > 0:
                         scale_x = w / canv_w
                         scale_y = h / canv_h
                         # Масштабируем центр собаки к координатам канваса для проверки
                         cx_canv = current_dog_center[0] / scale_x
                         cy_canv = current_dog_center[1] / scale_y
                         
                         if bx1 <= cx_canv <= bx2 and by1 <= cy_canv <= by2:
                             in_bed = True

                # Определение местоположения (для движения)
                h, w, _ = frame_to_process.shape
                location_str = ""
                if current_dog_center[1] < h / 2: location_str += "Верх"
                else: location_str += "Низ"
                if current_dog_center[0] < w / 2: location_str += "-Лево"
                else: location_str += "-Право"

                # Итоговый статус
                if in_bed:
                    status = "Спит/Лежит (на лежанке)" if not is_moving else "Возится на лежанке"
                elif is_moving:
                    status = f"Ходит [{location_str}]"
                else:
                    status = f"Стоит/Лежит [{location_str}]"

            # Сохраняем результаты для UI потока
            with self.lock:
                self.ai_results = {
                    'box': current_dog_box,
                    'text': status
                }
            
            # Счетчик FPS для ИИ
            frame_count += 1
            if time.time() - start_time > 1:
                fps = frame_count / (time.time() - start_time)
                # Обновляем FPS в UI потоке через after
                self.root.after(0, lambda f=fps: self.fps_label.config(text=f"FPS ИИ: {f:.1f}"))
                frame_count = 0
                start_time = time.time()
            
            # На CPU мы не спим, мы работаем на полную!

    def update_ui_loop(self):
        """Главный поток UI: рисует видео и накладывает графику"""
        if not self.is_camera_running:
            return

        frame_display = None
        with self.lock:
             if self.latest_frame_cv is not None:
                 frame_display = self.latest_frame_cv.copy()

        if frame_display is not None:
            # --- РИСОВАНИЕ ПОВЕРХ ВИДЕО ---
            
            # 1. Рисуем постоянную зону лежанки (если мониторинг активен)
            if self.is_ai_running and self.bed_zone:
                 # Преобразуем координаты канваса обратно в координаты кадра для OpenCV
                 h, w, _ = frame_display.shape
                 canv_w = self.canvas.winfo_width()
                 canv_h = self.canvas.winfo_height()
                 if canv_w > 0:
                     scale_x = w / canv_w
                     scale_y = h / canv_h
                     bx1, by1, bx2, by2 = self.bed_zone
                     cv2.rectangle(frame_display, 
                                 (int(bx1*scale_x), int(by1*scale_y)), 
                                 (int(bx2*scale_x), int(by2*scale_y)), 
                                 (0, 0, 255), 2) # Красный прямоугольник

            # 2. Рисуем результаты ИИ (если есть)
            ai_data = None
            with self.lock:
                ai_data = self.ai_results
            
            if self.is_ai_running and ai_data:
                box = ai_data.get('box')
                text = ai_data.get('text')
                
                # Обновляем статус на панели
                self.status_label.config(text=f"Собака: {text}")

                if box:
                    x1, y1, x2, y2 = box
                    # Зеленая рамка вокруг собаки
                    cv2.rectangle(frame_display, (x1, y1), (x2, y2), (0, 255, 0), 3)
                    # Текст с действием над рамкой (черный фон, белый текст)
                    (text_w, text_h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                    cv2.rectangle(frame_display, (x1, y1 - 30), (x1 + text_w, y1), (0, 255, 0), -1)
                    cv2.putText(frame_display, text, (x1, y1 - 8), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            # --- КОНВЕРТАЦИЯ И ОТОБРАЖЕНИЕ ---
            # OpenCV BGR -> PIL RGB -> Tkinter PhotoImage
            img = Image.fromarray(cv2.cvtColor(frame_display, cv2.COLOR_BGR2RGB))
            
            # Подгоняем под размер холста (если окно меняли)
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            if canvas_width > 1 and canvas_height > 1:
                 img = img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)

            imgtk = ImageTk.PhotoImage(image=img)
            
            # Отображаем на холсте
            self.canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
            self.canvas.image = imgtk # Важно: держим ссылку, чтобы не удалил сборщик мусора

            # Если мы в режиме настройки, временный красный квадрат рисуется сам средствами Canvas в обработчиках мыши

        # Планируем следующий кадр как можно скорее (для плавности видео)
        self.root.after(20, self.update_ui_loop)

if __name__ == "__main__":
    root = tk.Tk()
    app = SmartDogMonitor(root)
    # Корректное завершение при закрытии окна
    root.protocol("WM_DELETE_WINDOW", app.stop_all)
    root.mainloop()
