import argparse
import asyncio
import json
import logging
import os
import platform
import pyautogui
import pyperclip

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer

# Настройки
ROOT = os.path.dirname(__file__)
pyautogui.FAILSAFE = False

# Очередь соединений
pcs = set()

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    # --- НАСТРОЙКА ЗАХВАТА ЭКРАНА ---
    # Для Windows используем gdigrab (очень быстро)
    # Если нужно добавить звук, в options добавляются параметры dshow (сложно для новичка)
    if platform.system() == "Windows":
        # format='gdigrab' захватывает весь рабочий стол
        options = {"framerate": "30", "video_size": "1280x720"} # Можно менять разрешение
        player = MediaPlayer("desktop", format="gdigrab", options=options)
    else:
        # Для Linux/Mac нужны другие настройки (например x11grab)
        player = MediaPlayer("/dev/video0") # Заглушка для примера

    # Добавляем видео трек в WebRTC
    pc.addTrack(player.video)
    
    # --- Если получится настроить звук (раскомментировать при наличии навыков) ---
    # audio_player = MediaPlayer("audio=Stereo Mix (Realtek Audio)", format="dshow")
    # pc.addTrack(audio_player.audio)

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        if pc.iceConnectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}),
    )

async def control(request):
    """Принимает команды управления мышью и клавиатурой"""
    data = await request.json()
    action = data.get("type")
    
    screen_w, screen_h = pyautogui.size()

    if action == "mousemove":
        # Получаем координаты в процентах (0.0 - 1.0) и переводим в пиксели
        x = int(data["x"] * screen_w)
        y = int(data["y"] * screen_h)
        pyautogui.moveTo(x, y)

    elif action == "click":
        # Клик в текущей позиции (куда уже передвинули мышь)
        pyautogui.click()
    
    elif action == "keypress":
        key = data["key"]
        # Спец обработка для некоторых клавиш
        if key == "win": pyautogui.press("win")
        elif key == "space": pyautogui.press("space")
        else: pyautogui.press(key)
        
    elif action == "text":
        text = data["text"]
        # ХАК ДЛЯ РУССКОГО ТЕКСТА:
        # Копируем в буфер обмена и жмем Ctrl+V
        pyperclip.copy(text)
        pyautogui.hotkey('ctrl', 'v')

    return web.Response(text="OK")

async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r", encoding='utf-8').read()
    return web.Response(content_type="text/html", text=content)

async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)

if __name__ == "__main__":
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app.router.add_post("/control", control)
    app.on_shutdown.append(on_shutdown)
    
    print("🚀 Сервер запущен! Откройте в браузере: http://localhost:8080")
    web.run_app(app, host="0.0.0.0", port=8080)
