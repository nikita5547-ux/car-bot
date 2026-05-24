import os
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq
import json

logging.basicConfig(level=logging.INFO)

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS"]

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
        sheet.append_row(["Дата", "Тип", "Сумма", "Пробег"])
    return sheet

user_data = {}

MAIN_KEYBOARD = [["⛽ Заправка", "🚗 Расход"], ["📊 Статистика", "🕐 Последняя G-Drive"]]

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

    if text == "📊 Статистика":
        await show_stats(update, context)
        return

    if text == "🕐 Последняя G-Drive":
        await show_last_gdrive(update, context)
        return

    if user_id in user_data:
        data = user_data[user_id]

        if data["action"] == "fuel" and "fuel_type" not in data:
            if text in ["95", "G-Drive"]:
                data["fuel_type"] = text
                keyboard = [["◀️ Назад"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await update.message.reply_text("Сколько литров залил?", reply_markup=reply_markup)
                return

        if data["action"] == "fuel" and "fuel_type" in data and "liters" not in data:
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
                await update.message.reply_text("Текущий пробег (км)?")
                return
            except:
                await update.message.reply_text("Введи число, например: 52.5")
                return

        if data["action"] == "fuel" and "price" in data and "mileage" not in data:
            try:
                data["mileage"] = int(text.replace(" ", ""))
                total = round(data["liters"] * data["price"], 2)
                sheet = get_sheet()
                sheet.append_row([
                    datetime.now().strftime("%d.%m.%Y"),
                    data["fuel_type"],
                    data["liters"],
                    data["price"],
                    total,
                    data["mileage"]
                ])
                del user_data[user_id]
                reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
                await update.message.reply_text(
                    f"✅ Записано!\n{data['fuel_type']}, {data['liters']} л × {data['price']} ₽ = {total} ₽\nПробег: {data['mileage']} км",
                    reply_markup=reply_markup
                )
                return
            except:
                await update.message.reply_text("Введи число, например: 45000")
                return

        if data["action"] == "expense" and "expense_type" not in data:
            if text in ["Мойка", "Страховка", "Техосмотр", "Сервис"]:
                data["expense_type"] = text
                keyboard = [["◀️ Назад"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await update.message.reply_text("Сумма (₽)?", reply_markup=reply_markup)
                return

        if data["action"] == "expense" and "expense_type" in data and "amount" not in data:
            try:
                data["amount"] = float(text.replace(",", "."))
                await update.message.reply_text("Текущий пробег (км)?")
                return
            except:
                await update.message.reply_text("Введи число, например: 1500")
                return

        if data["action"] == "expense" and "amount" in data and "mileage" not in data:
            try:
                data["mileage"] = int(text.replace(" ", ""))
                sheet = get_expense_sheet()
                sheet.append_row([
                    datetime.now().strftime("%d.%m.%Y"),
                    data["expense_type"],
                    data["amount"],
                    data["mileage"]
                ])
                del user_data[user_id]
                reply_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)
                await update.message.reply_text(
                    f"✅ Записано!\n{data['expense_type']}: {data['amount']} ₽\nПробег: {data['mileage']} км",
                    reply_markup=reply_markup
                )
                return
            except:
                await update.message.reply_text("Введи число, например: 45000")
                return

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sheet = get_sheet()
        expense_sheet = get_expense_sheet()
        fuel_records = sheet.get_all_records()
        expense_records = expense_sheet.get_all_records()

        if not fuel_records:
            await update.message.reply_text("Пока нет данных о заправках.")
            return

        total_fuel_cost = sum(r["Сумма"] for r in fuel_records)
        total_liters = sum(r["Литры"] for r in fuel_records)
        gdrive_count = sum(1 for r in fuel_records if r["Тип топлива"] == "G-Drive")
        fuel_95_cost = sum(r["Сумма"] for r in fuel_records if r["Тип топлива"] == "95")
        gdrive_cost = sum(r["Сумма"] for r in fuel_records if r["Тип топлива"] == "G-Drive")
        total_expenses = sum(r["Сумма"] for r in expense_records) if expense_records else 0

        text = (
            f"📊 Статистика:\n\n"
            f"⛽ Всего потрачено на топливо: {total_fuel_cost:.0f} ₽\n"
            f"— 95: {fuel_95_cost:.0f} ₽\n"
            f"— G-Drive: {gdrive_cost:.0f} ₽ ({gdrive_count} раз)\n"
            f"Всего литров: {total_liters:.1f}\n\n"
            f"🚗 Прочие расходы: {total_expenses:.0f} ₽\n\n"
            f"💰 Итого на машину: {total_fuel_cost + total_expenses:.0f} ₽"
        )
        await update.message.reply_text(text)
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
