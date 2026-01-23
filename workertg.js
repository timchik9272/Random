export default {
  async fetch(request, env, ctx) {
    // 1. Проверяем, задан ли токен
    if (!env.BOT_TOKEN) {
      return new Response("Ошибка: BOT_TOKEN не найден в переменных", { status: 500 });
    }

    // Telegram отправляет запросы только методом POST
    if (request.method === "POST") {
      try {
        // Получаем данные от Телеграма (это JSON объект "Update")
        const payload = await request.json();

        // --- ЛОГИКА БОТА ---

        // СЛУЧАЙ А: Пользователь прислал сообщение (например, /start)
        if (payload.message && payload.message.text) {
          const chatId = payload.message.chat.id;
          const text = payload.message.text;

          if (text === "/start") {
            // Отправляем сообщение с кнопкой
            await sendTelegramRequest(env.BOT_TOKEN, "sendMessage", {
              chat_id: chatId,
              text: "Привет! Нажми на кнопку ниже:",
              reply_markup: {
                inline_keyboard: [
                  [
                    { text: "Кнопка 1", callback_data: "btn_1" },
                    { text: "Кнопка 2", callback_data: "btn_2" }
                  ],
                  [
                    { text: "Ссылка на Google", url: "https://google.com" }
                  ]
                ]
              }
            });
          } else {
             // Эхо на любой другой текст
             await sendTelegramRequest(env.BOT_TOKEN, "sendMessage", {
              chat_id: chatId,
              text: `Вы написали: ${text}`
            });
          }
        }

        // СЛУЧАЙ Б: Пользователь нажал на Inline-кнопку
        else if (payload.callback_query) {
          const chatId = payload.callback_query.message.chat.id;
          const data = payload.callback_query.data; // то, что написано в callback_data
          const callbackId = payload.callback_query.id;

          // Отвечаем пользователю
          await sendTelegramRequest(env.BOT_TOKEN, "sendMessage", {
            chat_id: chatId,
            text: `Вы нажали кнопку с данными: ${data}`
          });

          // Обязательно "гасим" часики загрузки на кнопке
          await sendTelegramRequest(env.BOT_TOKEN, "answerCallbackQuery", {
            callback_query_id: callbackId
          });
        }

      } catch (e) {
        // Если ошибка JSON или логики
        console.error(e);
      }
    }

    // Всегда возвращаем 200 OK Телеграму, иначе он будет дублировать сообщения
    return new Response("OK");
  },
};

// Вспомогательная функция для отправки запросов в Telegram API
async function sendTelegramRequest(token, method, body) {
  const url = `https://api.telegram.org/bot${token}/${method}`;
  return await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
}
