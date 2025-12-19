import asyncio
import io
import pyautogui
from PIL import ImageDraw
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = 'ВАШ_ТОКЕН_ЗДЕСЬ'  
ADMIN_ID = 123456789           # ВАШ ID

# Настройки управления
MOUSE_STEP = 50   # Шаг мыши (пиксели)
SCROLL_STEP = 300 # Шаг скролла

# Инициализация
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
pyautogui.FAILSAFE = False

# --- ФУНКЦИИ ---

def get_screenshot_with_cursor():
    """Делает скриншот, рисует на нем курсор и возвращает bytes"""
    # 1. Делаем скриншот
    image = pyautogui.screenshot()
    
    # 2. Узнаем где мышь
    cursor_x, cursor_y = pyautogui.position()
    
    # 3. Рисуем курсор (красный треугольник) прямо на изображении
    draw = ImageDraw.Draw(image)
    # Координаты треугольника курсора: (нос, лево-низ, право-низ)
    cursor_coords = [
        (cursor_x, cursor_y), 
        (cursor_x, cursor_y + 20), 
        (cursor_x + 15, cursor_y + 15)
    ]
    draw.polygon(cursor_coords, fill="red", outline="white")
    
    # 4. Сохраняем в память
    bio = io.BytesIO()
    image.save(bio, format='PNG')
    bio.seek(0)
    return bio

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    
    # 1 ряд: Скролл вверх и ОБНОВИТЬ
    builder.row(
        InlineKeyboardButton(text="scr ⬆️", callback_data="scroll_up"),
        InlineKeyboardButton(text="🔄", callback_data="refresh"), # Кнопка обновления
        InlineKeyboardButton(text="scr ⬇️", callback_data="scroll_down")
    )
    # 2 ряд: Движение мыши (Верх)
    builder.row(
        InlineKeyboardButton(text=" ", callback_data="ignore"), # Пустышка для отступа
        InlineKeyboardButton(text="⬆️", callback_data="mouse_up"),
        InlineKeyboardButton(text=" ", callback_data="ignore")
    )
    # 3 ряд: Влево - Вниз - Вправо
    builder.row(
        InlineKeyboardButton(text="⬅️", callback_data="mouse_left"),
        InlineKeyboardButton(text="⬇️", callback_data="mouse_down"),
        InlineKeyboardButton(text="➡️", callback_data="mouse_right")
    )
    # 4 ряд: Клики
    builder.row(
        InlineKeyboardButton(text="🟢 ЛКМ", callback_data="click_left"),
        InlineKeyboardButton(text="🔴 ПКМ", callback_data="click_right"),
        InlineKeyboardButton(text="⌨️ Keys", callback_data="menu_keys")
    )
    
    return builder.as_markup()

def get_keys_keyboard():
    builder = InlineKeyboardBuilder()
    keys = [
        ("Enter", "key_enter"), ("Backsp", "key_backspace"),
        ("Space", "key_space"), ("Esc", "key_esc"),
        ("Win", "key_win"), ("Alt+F4", "key_altf4"), 
        ("TaskMgr", "key_taskmgr"), ("🔄 Скрин", "refresh"), # И тут кнопка обновить
        ("🔙 Назад", "menu_main")
    ]
    for text, data in keys:
        builder.add(InlineKeyboardButton(text=text, callback_data=data))
    builder.adjust(2) 
    return builder.as_markup()

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    photo = get_screenshot_with_cursor()
    await message.answer_photo(
        photo=types.BufferedInputFile(photo.read(), filename="screen.png"),
        caption="🖥 Бот запущен. Курсор обозначен красным.",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query()
async def handle_callbacks(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return

    data = callback.data
    need_screen_update = False 

    # --- Обработка действий ---
    if data == "refresh":
        need_screen_update = True # Просто обновляем
    elif data == "ignore":
        await callback.answer()
        return

    # Мышь
    elif data == "mouse_up":
        pyautogui.moveRel(0, -MOUSE_STEP)
        need_screen_update = True
    elif data == "mouse_down":
        pyautogui.moveRel(0, MOUSE_STEP)
        need_screen_update = True
    elif data == "mouse_left":
        pyautogui.moveRel(-MOUSE_STEP, 0)
        need_screen_update = True
    elif data == "mouse_right":
        pyautogui.moveRel(MOUSE_STEP, 0)
        need_screen_update = True
    
    # Клики / Скролл
    elif data == "click_left":
        pyautogui.click()
        need_screen_update = True
    elif data == "click_right":
        pyautogui.click(button='right')
        need_screen_update = True
    elif data == "scroll_up":
        pyautogui.scroll(SCROLL_STEP)
        need_screen_update = True
    elif data == "scroll_down":
        pyautogui.scroll(-SCROLL_STEP)
        need_screen_update = True

    # Меню
    elif data == "menu_keys":
        await callback.message.edit_reply_markup(reply_markup=get_keys_keyboard())
    elif data == "menu_main":
        await callback.message.edit_reply_markup(reply_markup=get_main_keyboard())

    # Клавиши
    elif data.startswith("key_"):
        key = data.split("_")[1]
        if key == "altf4": pyautogui.hotkey('alt', 'f4')
        elif key == "taskmgr": pyautogui.hotkey('ctrl', 'shift', 'esc')
        else: pyautogui.press(key)
        need_screen_update = True

    # --- Обновление картинки ---
    if need_screen_update:
        try:
            new_photo_bytes = get_screenshot_with_cursor()
            media = InputMediaPhoto(
                media=types.BufferedInputFile(new_photo_bytes.read(), filename="update.png"),
                caption="✅ Обновлено"
            )
            await callback.message.edit_media(
                media=media, 
                reply_markup=callback.message.reply_markup
            )
        except TelegramBadRequest:
            # Если картинка не изменилась (Telegram не дает редактировать на то же самое)
            await callback.answer("Картинка не изменилась")
        except Exception as e:
            print(f"Error: {e}")

@dp.message()
async def type_text(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if message.text:
        pyautogui.write(message.text, interval=0.05)
        await message.reply(f"Напечатано: {message.text}")

# --- ЗАПУСК ---
async def main():
    print("Бот запущен...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
