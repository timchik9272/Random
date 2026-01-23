export default {
  async fetch(request, env, ctx) {
    // Проверка наличия переменных
    if (!env.BOT_TOKEN || !env.ADMIN_ID) {
      return new Response("Error: Переменные не заданы", { status: 500 });
    }

    if (request.method === "POST") {
      try {
        const payload = await request.json();
        await handleUpdate(payload, env);
      } catch (e) {
        console.error(e);
      }
    }
    return new Response("OK");
  },
};

async function handleUpdate(update, env) {
  // --- ОБРАБОТКА КОМАНД (/start и текст) ---
  if (update.message && update.message.text) {
    const chatId = update.message.chat.id;
    const userId = update.message.from.id;
    const text = update.message.text;

    // Проверяем, админ ли пишет (сравниваем как строки, чтобы избежать ошибок типов)
    const isAdmin = String(userId) === String(env.ADMIN_ID);

    if (text === "/start") {
      // 1. Формируем кнопки
      // Кнопка генератора есть у всех
      const keyboard = [
        [{ text: "🔐 Сгенерировать пароль", callback_data: "gen_pass" }]
      ];

      // 2. ЕСЛИ это админ, добавляем ему кнопку настроек
      if (isAdmin) {
        keyboard.push([{ text: "⚙️ Настройки / Uptime", callback_data: "admin_menu" }]);
      }

      await sendTelegram(env, "sendMessage", {
        chat_id: chatId,
        text: `Привет! Я бот-помощник.\n\nТвой статус: ${isAdmin ? "👑 Админ" : "👤 Пользователь"}`,
        reply_markup: { inline_keyboard: keyboard }
      });
    }

    // Обработка команд админа (например /check google.com)
    else if (text.startsWith("/check")) {
      if (!isAdmin) return; // Игнорируем обычных юзеров
      
      const url = text.split(" ")[1];
      if (!url) {
        await sendTelegram(env, "sendMessage", { chat_id: chatId, text: "Пример: /check google.com" });
      } else {
        await checkSite(chatId, url, env);
      }
    }
  }

  // --- ОБРАБОТКА КНОПОК ---
  else if (update.callback_query) {
    const cb = update.callback_query;
    const chatId = cb.message.chat.id;
    const messageId = cb.message.message_id;
    const data = cb.data;
    const userId = cb.from.id;
    const isAdmin = String(userId) === String(env.ADMIN_ID);

    // 1. Генерация пароля (Доступно всем)
    if (data === "gen_pass") {
      const password = generatePassword(12);
      // Если это админ, оставляем ему кнопку меню, если нет - только генератор
      const backButton = isAdmin ? [{ text: "🔙 В меню", callback_data: "go_start" }] : [];
      
      await sendTelegram(env, "editMessageText", {
        chat_id: chatId,
        message_id: messageId,
        text: `🔐 <b>Ваш новый пароль:</b>\n<code>${password}</code>`,
        parse_mode: "HTML",
        reply_markup: {
          inline_keyboard: [
            [{ text: "🔄 Еще один", callback_data: "gen_pass" }],
            backButton 
          ]
        }
      });
    }

    // 2. Главное меню (возврат)
    else if (data === "go_start") {
      const keyboard = [[{ text: "🔐 Сгенерировать пароль", callback_data: "gen_pass" }]];
      if (isAdmin) keyboard.push([{ text: "⚙️ Настройки / Uptime", callback_data: "admin_menu" }]);

      await sendTelegram(env, "editMessageText", {
        chat_id: chatId,
        message_id: messageId,
        text: "Главное меню:",
        reply_markup: { inline_keyboard: keyboard }
      });
    }

    // 3. Меню Админа (ТОЛЬКО ДЛЯ АДМИНА)
    else if (data === "admin_menu") {
      if (!isAdmin) return; // Защита от хакеров

      await sendTelegram(env, "editMessageText", {
        chat_id: chatId,
        message_id: messageId,
        text: "⚙️ <b>Панель Uptime</b>\nВыберите действие или отправьте команду <code>/check ссылка</code>",
        parse_mode: "HTML",
        reply_markup: {
          inline_keyboard: [
            [{ text: "🟢 Проверить Google", callback_data: "check_google" }],
            [{ text: "🔙 Назад", callback_data: "go_start" }]
          ]
        }
      });
    }

    // 4. Проверка Google по кнопке
    else if (data === "check_google") {
      if (!isAdmin) return;
      await sendTelegram(env, "answerCallbackQuery", { callback_query_id: cb.id, text: "Запрос отправлен..." });
      await checkSite(chatId, "https://google.com", env);
    }
  }
}

// --- ЛОГИКА ---

async function checkSite(chatId, url, env) {
  if (!url.startsWith("http")) url = "https://" + url;
  
  const start = Date.now();
  let textResult = "";
  
  try {
    const res = await fetch(url, { headers: {"User-Agent": "Bot"} });
    const time = Date.now() - start;
    const icon = res.status === 200 ? "✅" : "⚠️";
    textResult = `${icon} <b>${url}</b>\nСтатус: ${res.status}\nПинг: ${time}ms`;
  } catch (e) {
    textResult = `❌ <b>${url}</b>\nСайт лежит или недоступен.\nОшибка: ${e.message}`;
  }

  await sendTelegram(env, "sendMessage", {
    chat_id: chatId,
    text: textResult,
    parse_mode: "HTML"
  });
}

function generatePassword(len) {
  const chars = "abcdefhkmnpqrstuvwxyzABCDEFGHKMNPQRSTUVWXYZ23456789@#%";
  let pass = "";
  for (let i = 0; i < len; i++) pass += chars.charAt(Math.floor(Math.random() * chars.length));
  return pass;
}

// --- API TELEGRAM ---
async function sendTelegram(env, method, body) {
  return await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
            }
