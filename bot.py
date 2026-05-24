import os
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq
import json

logging.basicConfig(level=logging.INFO)

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS"]

def to_float(value):
    try:
        s = str(value).replace(" ", "")
        # Если есть запятая и точка — убираем запятую (разделитель тысяч)
        if "," in s and "." in s:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
        return float(s)
    except:
        return 0.0

def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(GOOGLE_CREDENTIALS)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    try:
        sheet = spreadsheet.worksheet("Заправки")
    except:
        sheet = spreadsheet.add_worksheet("Заправки", 1000, 10)
        sheet.append_row(["Дата", "Тип топлива", "Литры", "Цена за литр", "Сумма", "Пробег"])
    return sheet

def get_expense_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(GOOGLE_CREDENTIALS)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    try:
        sheet = spreadsheet.worksheet("Расходы")
    except:
        sheet = spreadsheet.add_worksheet("Расходы", 1000, 10)
        sheet.append_row(["Дата", "Тип", "Сумма", "Пробег", "Комментарий"])
    return sheet

def get_mileage_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(GOOGLE_CREDENTIALS)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    try:
        sheet = spreadsheet.worksheet("Пробег")
    except:
        sheet = spreadsheet.add_worksheet("Пробег", 1000, 5)
        sheet.append_row(["Дата", "Пробег"])
    return sheet

user_data = {}

MAIN_KEYBOARD = [
    ["⛽ Заправка", "🚗 Расход"],
    ["📍 Пробег", "📊 Статистика"],
    ["🕐 Последняя G-Drive"]
]
DATE_KEYBOARD = [["📅 Сегодня"], ["◀️ Назад"]]
MILEAGE_KEYBOARD = [["⏭ Пропустить"], ["◀️ Назад"]]
STATS_KEYBOARD = [
    ["Этот месяц", "Прошлый месяц"],
    ["3 месяца", "6 месяцев"],
    ["Год", "Свой период"],
    ["◀️ Назад"]
]

def parse_date(text):
    if text == "📅 Сегодня":
        return datetime.now().strftime("%d.%m.%Y")
    try:
        datetime.strptime(text, "%d.%m.%Y")
        return text
    except:
        return None

def get_period(text):
    now = datetime.now()
    if text == "Этот месяц":
        start = now.replace(day=1)
        end = now
    elif text == "Прошлый месяц":
        first_this = now.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        start = last_prev.replace(day=1)
        end = last_prev
    elif text == "3 месяца":
        start = now - timedelta(days=90)
        end = now
    elif text == "6 месяцев":
        start = now - timedelta(days=180)
        end = now
    elif text == "Год":
        start = now - timedelta(days=365)
        end = now
    else:
        return None, None
    return start.strftime("%d.%m.%Y"), end.strftime("%d.%m.%Y")

def filter_by_period(records, date_from, date_to):
    d_from = datetime.strptime(date_from, "%d.%m.%Y")
    d_to = datetime.strptime(date_to, "%d.%m.%Y")
    result = []
    for r in records:
        try:
            d = datetime.strptime(r["Дата"], "%d.%m.%Y")
            if d_from <= d <= d_to:
                result.append(r)
        except:
            pass
    return result

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
    await update.message.reply_text("Привет! Я бот для учёта расходов на машину. Выбери действие:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id

    if text == "◀️ Назад":
        if user_id in user_data:
            del user_data[user_id]
        reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)
        return

    if text == "⛽ Заправка":
        keyboard = [["95", "G-Drive"], ["◀️ Назад"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Какое топливо?", reply_markup=reply_markup)
        user_data[user_id] = {"action": "fuel"}
        return

    if text == "🚗 Расход":
        keyboard = [["Мойка", "Страховка"], ["Техосмотр", "Сервис"], ["◀️ Назад"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Тип расхода?", reply_markup=reply_markup)
        user_data[user_id] = {"action": "expense"}
        return

    if text == "📍 Пробег":
        reply_markup = ReplyKeyboardMarkup(DATE_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text(
            "Дата?\nНажми «Сегодня» или введи вручную (например: 23.05.2026)",
            reply_markup=reply_markup
        )
        user_data[user_id] = {"action": "mileage_log"}
        return

    if text == "📊 Статистика":
        reply_markup = ReplyKeyboardMarkup(STATS_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text("За какой период?", reply_markup=reply_markup)
        user_data[user_id] = {"action": "stats"}
        return

    if text == "🕐 Последняя G-Drive":
        await show_last_gdrive(update, context)
        return

    if user_id in user_data:
        data = user_data[user_id]

        # ЗАПИСЬ ПРОБЕГА
        if data["action"] == "mileage_log" and "date" not in data:
            date = parse_date(text)
            if date:
                data["date"] = date
                keyboard = [["◀️ Назад"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await update.message.reply_text("Текущий пробег (км)?", reply_markup=reply_markup)
                return
            else:
                await update.message.reply_text("Неверный формат. Введи дату как 23.05.2026 или нажми «Сегодня»")
                return

        if data["action"] == "mileage_log" and "date" in data:
            try:
                mileage = int(text.replace(" ", ""))
                sheet = get_mileage_sheet()
                sheet.append_row([data["date"], mileage])
                del user_data[user_id]
                reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
                await update.message.reply_text(f"✅ Пробег записан!\nДата: {data['date']}\nПробег: {mileage} км", reply_markup=reply_markup)
                return
            except:
                await update.message.reply_text("Введи число, например: 45000")
                return

        # СТАТИСТИКА
        if data["action"] == "stats" and "date_from" not in data:
            if text == "Свой период":
                data["custom_period"] = True
                keyboard = [["◀️ Назад"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await update.message.reply_text("Введи дату начала (например: 01.01.2026):", reply_markup=reply_markup)
                return
            elif text in ["Этот месяц", "Прошлый месяц", "3 месяца", "6 месяцев", "Год"]:
                date_from, date_to = get_period(text)
                await show_stats(update, context, date_from, date_to)
                del user_data[user_id]
                return

        if data["action"] == "stats" and data.get("custom_period") and "date_from" not in data:
            try:
                datetime.strptime(text, "%d.%m.%Y")
                data["date_from"] = text
                await update.message.reply_text("Введи дату конца (например: 24.05.2026):")
                return
            except:
                await update.message.reply_text("Неверный формат. Введи как 01.01.2026")
                return

        if data["action"] == "stats" and "date_from" in data and "date_to" not in data:
            try:
                datetime.strptime(text, "%d.%m.%Y")
                data["date_to"] = text
                await show_stats(update, context, data["date_from"], data["date_to"])
                del user_data[user_id]
                return
            except:
                await update.message.reply_text("Неверный формат. Введи как 24.05.2026")
                return

        # ЗАПРАВКА
        if data["action"] == "fuel" and "fuel_type" not in data:
            if text in ["95", "G-Drive"]:
                data["fuel_type"] = text
                reply_markup = ReplyKeyboardMarkup(DATE_KEYBOARD, resize_keyboard=True)
                await update.message.reply_text(
                    "Дата заправки?\nНажми «Сегодня» или введи вручную (например: 23.05.2026)",
                    reply_markup=reply_markup
                )
                return

        if data["action"] == "fuel" and "fuel_type" in data and "date" not in data:
            date = parse_date(text)
            if date:
                data["date"] = date
                keyboard = [["◀️ Назад"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await update.message.reply_text("Сколько литров залил?", reply_markup=reply_markup)
                return
            else:
                await update.message.reply_text("Неверный формат. Введи дату как 23.05.2026 или нажми «Сегодня»")
                return

        if data["action"] == "fuel" and "date" in data and "liters" not in data:
            try:
                data["liters"] = float(text.replace(",", "."))
                await update.message.reply_text("Цена за литр?")
                return
            except:
                await update.message.reply_text("Введи число, например: 52.5")
                return

        if data["action"] == "fuel" and "liters" in data and "price" not in data:
            try:
                data["price"] = float(text.replace(",", "."))
                reply_markup = ReplyKeyboardMarkup(MILEAGE_KEYBOARD, resize_keyboard=True)
                await update.message.reply_text("Текущий пробег (км)?", reply_markup=reply_markup)
                return
            except:
                await update.message.reply_text("Введи число, например: 52.5")
                return

        if data["action"] == "fuel" and "price" in data and "mileage" not in data:
            if text == "⏭ Пропустить":
                data["mileage"] = ""
            else:
                try:
                    data["mileage"] = int(text.replace(" ", ""))
                except:
                    await update.message.reply_text("Введи число, например: 45000")
                    return
            total = round(data["liters"] * data["price"], 2)
            sheet = get_sheet()
            sheet.append_row([data["date"], data["fuel_type"], data["liters"], data["price"], total, data["mileage"]])
            del user_data[user_id]
            reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
            mileage_text = f"\nПробег: {data['mileage']} км" if data["mileage"] != "" else ""
            await update.message.reply_text(
                f"✅ Записано!\n{data['fuel_type']}, {data['liters']} л × {data['price']} ₽ = {total} ₽\nДата: {data['date']}{mileage_text}",
                reply_markup=reply_markup
            )
            return

        # РАСХОДЫ
        if data["action"] == "expense" and "expense_type" not in data:
            if text in ["Мойка", "Страховка", "Техосмотр", "Сервис"]:
                data["expense_type"] = text
                reply_markup = ReplyKeyboardMarkup(DATE_KEYBOARD, resize_keyboard=True)
                await update.message.reply_text(
                    "Дата?\nНажми «Сегодня» или введи вручную (например: 23.05.2026)",
                    reply_markup=reply_markup
                )
                return

        if data["action"] == "expense" and "expense_type" in data and "date" not in data:
            date = parse_date(text)
            if date:
                data["date"] = date
                keyboard = [["◀️ Назад"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await update.message.reply_text("Сумма (₽)?", reply_markup=reply_markup)
                return
            else:
                await update.message.reply_text("Неверный формат. Введи дату как 23.05.2026 или нажми «Сегодня»")
                return

        if data["action"] == "expense" and "date" in data and "amount" not in data:
            try:
                data["amount"] = float(text.replace(",", "."))
                reply_markup = ReplyKeyboardMarkup(MILEAGE_KEYBOARD, resize_keyboard=True)
                await update.message.reply_text("Текущий пробег (км)?", reply_markup=reply_markup)
                return
            except:
                await update.message.reply_text("Введи число, например: 1500")
                return

        if data["action"] == "expense" and "amount" in data and "mileage" not in data:
            if text == "⏭ Пропустить":
                data["mileage"] = ""
            else:
                try:
                    data["mileage"] = int(text.replace(" ", ""))
                except:
                    await update.message.reply_text("Введи число, например: 45000")
                    return

            if data["expense_type"] in ["Сервис", "Техосмотр"]:
                data["mileage_saved"] = data["mileage"]
                keyboard = [["⏭ Пропустить"], ["◀️ Назад"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await update.message.reply_text("Комментарий (что сделали)?", reply_markup=reply_markup)
                return
            else:
                data["comment"] = ""
                sheet = get_expense_sheet()
                sheet.append_row([data["date"], data["expense_type"], data["amount"], data["mileage"], data["comment"]])
                del user_data[user_id]
                reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
                mileage_text = f"\nПробег: {data['mileage']} км" if data["mileage"] != "" else ""
                await update.message.reply_text(
                    f"✅ Записано!\n{data['expense_type']}: {data['amount']} ₽\nДата: {data['date']}{mileage_text}",
                    reply_markup=reply_markup
                )
                return

        if data["action"] == "expense" and "mileage_saved" in data and "comment" not in data:
            data["comment"] = "" if text == "⏭ Пропустить" else text
            sheet = get_expense_sheet()
            sheet.append_row([data["date"], data["expense_type"], data["amount"], data["mileage_saved"], data["comment"]])
            del user_data[user_id]
            reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
            mileage_text = f"\nПробег: {data['mileage_saved']} км" if data["mileage_saved"] != "" else ""
            comment_text = f"\nКомментарий: {data['comment']}" if data["comment"] else ""
            await update.message.reply_text(
                f"✅ Записано!\n{data['expense_type']}: {data['amount']} ₽\nДата: {data['date']}{mileage_text}{comment_text}",
                reply_markup=reply_markup
            )
            return

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, date_from: str, date_to: str):
    try:
        sheet = get_sheet()
        expense_sheet = get_expense_sheet()
        fuel_records = filter_by_period(sheet.get_all_records(), date_from, date_to)
        await update.message.reply_text(f"Сырые данные: {fuel_records}")
        expense_records = filter_by_period(expense_sheet.get_all_records(), date_from, date_to)

        total_fuel_cost = sum(to_float(r["Сумма"]) for r in fuel_records)
        total_liters = sum(to_float(r["Литры"]) for r in fuel_records)
        gdrive_count = sum(1 for r in fuel_records if r["Тип топлива"] == "G-Drive")
        fuel_95_cost = sum(to_float(r["Сумма"]) for r in fuel_records if r["Тип топлива"] == "95")
        gdrive_cost = sum(to_float(r["Сумма"]) for r in fuel_records if r["Тип топлива"] == "G-Drive")
        total_expenses = sum(to_float(r["Сумма"]) for r in expense_records) if expense_records else 0

        mileage_records = [r for r in fuel_records if r.get("Пробег") not in ["", None]]
        cost_per_km_text = ""
        if len(mileage_records) >= 2:
            try:
                first_mileage = int(str(mileage_records[0]["Пробег"]).replace(" ", ""))
                last_mileage = int(str(mileage_records[-1]["Пробег"]).replace(" ", ""))
                total_km = last_mileage - first_mileage
                if total_km > 0:
                    cost_per_km = round((total_fuel_cost + total_expenses) / total_km, 2)
                    cost_per_km_text = f"\n📍 Стоимость км: {cost_per_km} ₽"
            except:
                pass

        text = (
            f"📊 Статистика за {date_from} — {date_to}:\n\n"
            f"⛽ Топливо: {total_fuel_cost:.0f} ₽\n"
            f"— 95: {fuel_95_cost:.0f} ₽\n"
            f"— G-Drive: {gdrive_cost:.0f} ₽ ({gdrive_count} раз)\n"
            f"Всего литров: {total_liters:.1f}\n\n"
            f"🚗 Прочие расходы: {total_expenses:.0f} ₽\n\n"
            f"💰 Итого: {total_fuel_cost + total_expenses:.0f} ₽"
            f"{cost_per_km_text}"
        )
        reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
        await update.message.reply_text(text, reply_markup=reply_markup)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def show_last_gdrive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        gdrive_records = [r for r in records if r["Тип топлива"] == "G-Drive"]
        if not gdrive_records:
            await update.message.reply_text("G-Drive ещё не заливал.")
            return
        last = gdrive_records[-1]
        await update.message.reply_text(
            f"🕐 Последний G-Drive:\nДата: {last['Дата']}\nЛитры: {last['Литры']}\nСумма: {last['Сумма']} ₽\nПробег: {last['Пробег']} км"
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.run_polling()
