#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <UniversalTelegramBot.h>
#include <DHT.h>

// WiFi credentials
#define WIFI_SSID "AMR273"
#define WIFI_PASSWORD "amr41amr123456789"

// Telegram BOT Token
#define BOT_TOKEN "7318549028:AAEL3WnLTylBkYWHub0tx8VpMGHTRaKHDCk"

// DHT sensor pin and type
#define SENSOR_PIN D3
#define DHTTYPE DHT22   // DHT 22 (AM2302), or DHT11

// Admin ID
#define ADMIN_ID 5481803813

// Anti-spam settings
#define MAX_MESSAGES 5
#define TIME_WINDOW 10000  // 10 seconds
#define BAN_DURATION 300000  // 5 minutes

DHT dht(SENSOR_PIN, DHTTYPE);

WiFiClientSecure secured_client;
UniversalTelegramBot bot(BOT_TOKEN, secured_client);

// Settings (volatile, reset on reboot)
String allowedUsers = "5481803813";  // Default: only admin, or "all" for everyone
bool notificationsEnabled = true;

// Anti-spam tracking (support up to 10 users for simplicity)
struct UserSpamInfo {
  long id;
  unsigned long lastTime;
  int count;
  unsigned long banUntil;
};
UserSpamInfo users[10];
int numUsers = 0;

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  secured_client.setInsecure();  // Skip certificate validation (for simplicity)

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
  Serial.println("WiFi connected");

  dht.begin();
}

void loop() {
  int numNewMessages = bot.getUpdates(bot.last_message_received + 1);
  handleNewMessages(numNewMessages);
  delay(1000);  // Poll every second
}

void handleNewMessages(int numNewMessages) {
  for (int i = 0; i < numNewMessages; i++) {
    String chat_id = bot.messages[i].chat_id;
    long user_id = bot.messages[i].from_id.toInt(); // Convert String to long
    String text = bot.messages[i].text;
    String message_id = String(bot.messages[i].message_id); // Convert int to String
    String message_type = bot.messages[i].type;

    // Check if banned
    UserSpamInfo* user = getUserInfo(user_id);
    if (millis() < user->banUntil) {
      bot.sendMessage(chat_id, "Вы забанены на " + String((user->banUntil - millis()) / 60000) + " минут. ⏰", "");
      continue;
    }

    // Update spam count
    updateSpam(user);

    // Check spam
    if (user->count > MAX_MESSAGES) {
      user->banUntil = millis() + BAN_DURATION;
      bot.sendMessage(chat_id, "Обнаружен спам! Забанены на 5 минут. 🚫", "");
      if (notificationsEnabled) {
        bot.sendMessage(String(ADMIN_ID), "Пользователь " + String(user_id) + " забанен за спам. ⚠️", "");
      }
      continue;
    }

    // Forward to admin if not from admin and notifications enabled
    if (user_id != ADMIN_ID && notificationsEnabled) {
      bot.sendMessage(String(ADMIN_ID), "От " + String(user_id) + ": " + text + " 📩", "");
    }

    // Check if allowed
    bool allowed = isAllowed(user_id);
    if (!allowed) {
      bot.sendMessage(chat_id, "Вы не имеете доступа к боту. 🚫", "");
      continue;
    }

    if (message_type == "callback_query") {
      String callback_data = text;  // callback_data is in text for queries
      String query_id = message_id;  // Use message_id for callback query

      if (callback_data == "update") {
        String data = getTemperatureAndHumidity();
        bot.answerCallbackQuery(query_id, "Данные обновлены! 🔄");
        bot.sendMessageWithInlineKeyboard(chat_id, data, "", getInlineKeyboard(user_id == ADMIN_ID), bot.messages[i].message_id);
      } else if (callback_data == "admin_panel" && user_id == ADMIN_ID) {
        bot.answerCallbackQuery(query_id, "Открываем админ-панель ⚙️");
        String adminText = "Админ-панель ⚙️";
        bot.sendMessageWithInlineKeyboard(chat_id, adminText, "", getAdminKeyboard(), bot.messages[i].message_id);
      } else if (callback_data == "toggle_notif" && user_id == ADMIN_ID) {
        notificationsEnabled = !notificationsEnabled;
        bot.answerCallbackQuery(query_id, "Уведомления " + String(notificationsEnabled ? "включены ✅" : "выключены ❌"));
        String adminText = "Админ-панель ⚙️";
        bot.sendMessageWithInlineKeyboard(chat_id, adminText, "", getAdminKeyboard(), bot.messages[i].message_id);
      } else if (callback_data == "set_allowed" && user_id == ADMIN_ID) {
        bot.answerCallbackQuery(query_id, "Отправьте /setallowed <ids> или /setallowed all 📝");
      } else if (callback_data == "back" && user_id == ADMIN_ID) {
        bot.answerCallbackQuery(query_id, "Возврат к главному меню ⬅️");
        String data = getTemperatureAndHumidity();
        bot.sendMessageWithInlineKeyboard(chat_id, data, "", getInlineKeyboard(true), bot.messages[i].message_id);
      }

      continue;
    }

    // Handle commands
    if (text == "/start") {
      String data = getTemperatureAndHumidity();
      bot.sendMessageWithInlineKeyboard(chat_id, data, "", getInlineKeyboard(user_id == ADMIN_ID));
    } else if (text.startsWith("/setallowed") && user_id == ADMIN_ID) {
      String args = text.substring(12);  // Skip "/setallowed "
      if (args.length() > 0) {
        allowedUsers = args;
        bot.sendMessage(chat_id, "Разрешённые пользователи установлены: " + allowedUsers + " ✅", "");
      } else {
        bot.sendMessage(chat_id, "Использование: /setallowed id1,id2,... или all 📝", "");
      }
    } else {
      bot.sendMessage(chat_id, "Команда не распознана. Используйте /start. ❓", "");
    }
  }
}

String getInlineKeyboard(bool isAdmin) {
  if (isAdmin) {
    return "{\"inline_keyboard\":[[{\"text\":\"Обновить 🔄\",\"callback_data\":\"update\"},{\"text\":\"Админ-панель ⚙️\",\"callback_data\":\"admin_panel\"}]]}";
  } else {
    return "{\"inline_keyboard\":[[{\"text\":\"Обновить 🔄\",\"callback_data\":\"update\"}]]}";
  }
}

String getAdminKeyboard() {
  String status = notificationsEnabled ? "Выключить уведомления ❌" : "Включить уведомления ✅";
  return "{\"inline_keyboard\":[[{\"text\":\"" + status + "\",\"callback_data\":\"toggle_notif\"},{\"text\":\"Установить разрешённых 📝\",\"callback_data\":\"set_allowed\"}],[{\"text\":\"Назад ⬅️\",\"callback_data\":\"back\"}]]}";
}

bool isAllowed(long id) {
  if (allowedUsers == "all") return true;
  return allowedUsers.indexOf(String(id)) != -1;
}

String getTemperatureAndHumidity() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) {
    return "Ошибка чтения датчика ⚠️";
  }
  return "Температура: " + String(t) + " °C 🌡️\nВлажность: " + String(h) + " % 💧";
}

UserSpamInfo* getUserInfo(long id) {
  for (int j = 0; j < numUsers; j++) {
    if (users[j].id == id) return &users[j];
  }
  if (numUsers < 10) {
    users[numUsers].id = id;
    users[numUsers].lastTime = millis();
    users[numUsers].count = 0;
    users[numUsers].banUntil = 0;
    return &users[numUsers++];
  }
  // Overflow: use last
  return &users[9];
}

void updateSpam(UserSpamInfo* user) {
  unsigned long now = millis();
  if (now - user->lastTime > TIME_WINDOW) {
    user->count = 1;
    user->lastTime = now;
  } else {
    user->count++;
  }
}
