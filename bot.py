import telebot
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import psycopg2 as sql
import logging
import os
import time
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import pytz
from telebot.types import ReplyKeyboardMarkup

# Создаем объект часовой зоны для UTC+5
almaty_timezone = pytz.timezone('Asia/Almaty')

# Инициализируем планировщик задач
scheduler = BackgroundScheduler()
scheduler.start()

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv('envPath')
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
telebot.apihelper.READ_TIMEOUT = 35


def create_connection():
    try:
        conn = sql.connect(
            dbname="base_name",
            user="postgres",
            password="password",
            host="127.0.0.1",
        )
        return conn
    except Exception as e:
        logger.error("Ошибка подключения к базе данных: {}".format(e))
        return None


# Настройка WebDriver для Selenium
def setupBrowser():
    edgeOptions = Options()
    edgeOptions.use_chromium = True
    edgeOptions.add_argument("--headless")  # Добавление опции для запуска в headless режиме
    edgeOptions.add_argument("--disable-gpu")  # Отключение GPU для дополнительной стабильности в headless режиме
    edgeOptions.add_argument("--window-size=1920,1200")  # Установка размера окна (необходимо для некоторых страниц)

    edgeService = Service(executable_path=os.getenv('EDGE_DRIVER_PATH'))
    browser = webdriver.Edge(service=edgeService, options=edgeOptions)
    return browser


# Функция для получения и сохранения расписания
def fetchSchedule(login, password, user_id):
    conn = create_connection()
    cursor = conn.cursor()
    browser = setupBrowser()
    try:
        browser.get('https://platonus.iitu.edu.kz')
        WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.ID, "login_input")))
        logger.info("Login input found")
        browser.find_element(By.ID, 'login_input').send_keys(login)
        browser.find_element(By.ID, 'pass_input').send_keys(password)
        browser.find_element(By.ID, 'Submit1').click()
        time.sleep(5)

        newButton = WebDriverWait(browser, 10).until(EC.element_to_be_clickable((By.XPATH, "//a[@href='/v7/#/map']")))
        newButton.click()

        time.sleep(3)

        scheduleLink = WebDriverWait(browser, 10).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "a.link-info.ng-star-inserted[href='/v7/#/schedule/studentView']"))
        )
        scheduleLink.click()

        logger.info("Waiting for the schedule page to load...")
        time.sleep(5)  # Задержка для полной загрузки страницы расписания

        html = browser.page_source
        soup = BeautifulSoup(html, 'html.parser')
        # todayDayName = datetime.now().strftime('%A')
        dayNameTranslation = {
            'Monday': 'Понедельник',
            'Tuesday': 'Вторник',
            'Wednesday': 'Среда',
            'Thursday': 'Четверг',
            'Friday': 'Пятница',
            'Saturday': 'Суббота',
            'Sunday': 'Воскресенье'
        }
        # todayDayNameRu = dayNameTranslation[todayDayName]

        for _, dayOfWeek in dayNameTranslation.items():
            day_heading = soup.find('h5', string=dayOfWeek)
            if day_heading:
                daySchedule = day_heading.find_next_sibling('div', class_='table-responsive')
                if daySchedule:
                    rows = daySchedule.find_all('tr', class_='ng-star-inserted')
                    for row in rows:
                        timeSlot = row.find('td', style='width: 20%;').text.strip() if row.find('td',
                                                                                                style='width: 20%;') else "Не указано время"
                        # Извлекаем только начальное время из интервала
                        start_time = timeSlot.split(' - ')[0] if timeSlot and '-' in timeSlot else timeSlot
                        lessonDescriptionElement = row.find('div', class_='ng-star-inserted')
                        if lessonDescriptionElement:
                            # Получаем весь текст после времени
                            lessonDescription = ' '.join(lessonDescriptionElement.text.strip().split()[0:])
                            # lessonDescription += '(университет)'
                        else:
                            lessonDescription = "Описание отсутствует"

                        if lessonDescription and not lessonDescription.isspace():
                            cursor.execute("""
                                INSERT INTO user_events (user_id, day_of_week, event_time, event_description)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (user_id, day_of_week, event_time)
                                DO UPDATE SET event_description = EXCLUDED.event_description;
                            """, (user_id, dayOfWeek, start_time, lessonDescription))
                            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка при получении расписания: {e}")
        return "Не удалось получить расписание."
    finally:
        browser.quit()
        cursor.close()
        conn.close()
    return "Расписание успешно обновлено"


# Обработка команды /start
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.add('1. Добавить свое событие', '2. Выгрузить из Platonus', '3. Удалить событие', '4. Удаление всех событий', '5. Просмотр событий')
    msg = bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_option_selection, message.chat.id)


def process_option_selection(message, user_id):
    if message.text == '1. Добавить свое событие':
        msg = bot.send_message(user_id, "Введите событие в формате 'День недели HH:MM Описание'")
        bot.register_next_step_handler(msg, add_custom_event, user_id)
    elif message.text == '2. Выгрузить из Platonus':
        msg = bot.send_message(user_id, "Отправьте ваш логин и пароль от Platonus в формате: логин;пароль")
        bot.register_next_step_handler(msg, fetch_platonus_schedule, user_id)
    elif message.text == '3. Удалить событие':
        msg = bot.send_message(user_id,"Введите время и первое слово описания события для удаления в формате 'HH:MM;Первое слово'")
        bot.register_next_step_handler(msg, delete_event, user_id)
    elif message.text == '4. Удаление всех событий':
        delete_all_events(user_id)
    elif message.text == '5. Просмотр событий':
        show_schedule_selection(user_id)


def delete_all_events(user_id):
    conn = create_connection()
    if not conn:
        bot.send_message(user_id, "Ошибка подключения к базе данных.")
        return
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM user_events WHERE user_id = %s", (user_id,))
        conn.commit()
        if cursor.rowcount > 0:
            bot.send_message(user_id, "Все ваши события успешно удалены.")
        else:
            bot.send_message(user_id, "События для удаления не найдены.")
    except Exception as e:
        logger.error("Ошибка при удалении всех событий: {}".format(e))
        bot.send_message(user_id, "Произошла ошибка при удалении всех событий.")
    finally:
        cursor.close()
        if conn:
            conn.close()


def show_schedule_selection(user_id):
    days_of_week = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    for day in days_of_week:
        markup.add(day)
    msg = bot.send_message(user_id, "Выберите день недели:", reply_markup=markup)
    bot.register_next_step_handler(msg, show_schedule, user_id)


def show_schedule(message, user_id):
    day_of_week = message.text
    conn = create_connection()
    if conn is None:
        bot.send_message(user_id, "Ошибка подключения к базе данных.")
        return
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT event_time, event_description FROM user_events WHERE user_id = %s AND day_of_week = %s ORDER BY event_time", (user_id, day_of_week))
        events = cursor.fetchall()
        if events:
            schedule_text = f"Расписание на {day_of_week}:\n"
            schedule_text += "\n".join([f"{time} - {desc}" for time, desc in events])
            bot.send_message(user_id, schedule_text)
        else:
            bot.send_message(user_id, "На выбранный день событий не найдено.")
    except Exception as e:
        logger.error(f"Ошибка при получении расписания: {e}")
        bot.send_message(user_id, "Произошла ошибка при получении расписания.")
    finally:
        cursor.close()
        conn.close()


def delete_event(message, user_id):
    try:
        time, first_word = message.text.split(';')
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_events WHERE user_id = %s AND event_time = %s AND event_description LIKE %s", (user_id, time, first_word + '%'))
        conn.commit()
        if cursor.rowcount > 0:
            bot.send_message(user_id, "Событие успешно удалено.")
        else:
            bot.send_message(user_id, "Событие не найдено.")
    except Exception as e:
        logger.error("Ошибка при удалении события: {}".format(e))
        bot.send_message(user_id, "Произошла ошибка при удалении события.")
    finally:
        if conn:
            conn.close()


def add_custom_event(message, user_id):
    conn = create_connection()
    cursor = conn.cursor()
    try:
        # Разбиваем сообщение на части
        parts = message.text.split(' ', 2)
        if len(parts) != 3:
            bot.send_message(user_id, "Пожалуйста, отправьте данные в формате 'День недели HH:MM Описание'")
            return

        day_of_week, event_time, event_description = parts

        # Проверяем, что день недели валиден
        dayNameTranslation = {
            'Monday': 'Понедельник',
            'Tuesday': 'Вторник',
            'Wednesday': 'Среда',
            'Thursday': 'Четверг',
            'Friday': 'Пятница',
            'Saturday': 'Суббота',
            'Sunday': 'Воскресенье'
        }

        # Проверяем, что введенный день недели соответствует одному из ключей словаря
        if day_of_week not in dayNameTranslation.values():
            bot.send_message(user_id, "День недели должен быть одним из следующих: " + ', '.join(dayNameTranslation.values()))
            return

        # Проверяем корректность времени
        try:
            time.strptime(event_time, '%H:%M')  # Проверяем, что время в правильном формате
        except ValueError:
            bot.send_message(user_id, "Время должно быть в формате HH:MM")
            return

        # Добавляем событие в базу данных
        cursor.execute("""
            INSERT INTO user_events (user_id, day_of_week, event_time, event_description)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, day_of_week, event_time)
            DO UPDATE SET event_description = EXCLUDED.event_description;
        """, (user_id, day_of_week, event_time, event_description))
        conn.commit()

        bot.send_message(user_id, "Событие успешно добавлено!")
    except Exception as e:
        logger.error(f"Ошибка при добавлении события: {e}")
        bot.send_message(user_id, "Произошла ошибка при добавлении события.")
    finally:
        cursor.close()
        conn.close()


def fetch_platonus_schedule(message, user_id):
    credentials = message.text.split(';')
    if len(credentials) != 2:
        bot.send_message(user_id, "Пожалуйста, используйте формат: логин;пароль")
        return
    login, password = credentials
    result = fetchSchedule(login, password, user_id)
    bot.send_message(user_id, result)


# Словарь для перевода дней недели с русского на английский
day_name_translation = {
    'Понедельник': 'Monday',
    'Вторник': 'Tuesday',
    'Среда': 'Wednesday',
    'Четверг': 'Thursday',
    'Пятница': 'Friday',
    'Суббота': 'Saturday',
    'Воскресенье': 'Sunday',
}


# Функция отправки уведомления пользователю через Telegram.
def notify_user(user_id, description):
    try:
        message = f"Ваше событие '{description}' начнется через 20 минут."
        bot.send_message(user_id, message)
        logger.info(f"Уведомление отправлено пользователю {user_id}.")
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")


# Функция для отправки напоминаний
def send_reminders():
    conn = create_connection()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        now = datetime.now(almaty_timezone)
        check_time = (now + timedelta(minutes=20)).strftime('%H:%M')

        # Получаем день недели из базы данных на английском
        current_day_english = now.strftime('%A')  # Получаем текущий день недели на английском

        # Проверяем, есть ли соответствие в словаре
        if current_day_english not in day_name_translation.values():
            logger.error(f"День недели '{current_day_english}' не найден в словаре.")
            return

        # Переводим день недели на русский
        for key, value in day_name_translation.items():
            if value == current_day_english:
                current_day_russian = key

        if not current_day_russian:
            raise ValueError("День недели не найден в словаре перевода.")

        # Выборка событий, которые должны начаться через 30 минут
        cursor.execute(
            "SELECT user_id, event_description FROM user_events WHERE day_of_week = %s AND event_time = %s;",
            (current_day_russian, check_time)
        )

        events = cursor.fetchall()

        for user_id, description in events:
            notify_user(user_id, description)

    except Exception as e:
        logger.error(f"Ошибка при отправке напоминаний: {e}")
    finally:
        cursor.close()
        conn.close()


# Настройка задачи на выполнение каждую минуту
scheduler.add_job(send_reminders, 'cron', minute='*')


if __name__ == '__main__':
    bot.polling(non_stop=True)
