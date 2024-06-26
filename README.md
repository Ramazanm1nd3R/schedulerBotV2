# Telegram Bot Project

## Описание
Этот проект включает в себя разработку Telegram бота, который предназначен для работы с расписаниями и другими пользовательскими данными. Бот использует Selenium для взаимодействия с веб-страницами и получения актуальной информации, а также PostgreSQL для хранения данных.

## Настройка

### Предварительные требования
- Python 3.8+
- PostgreSQL
- Selenium WebDriver

### Установка
1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/Ramazanm1nd3R/schedulerTelegBot.git
2. Установите зависимости:
   ```
   pip install -r requirements.txt

Конфигурация
Создайте файл .env в корневом каталоге проекта с следующими переменными окружения:

* TELEGRAM_BOT_TOKEN - токен вашего бота от BotFather.
* DATABASE_URL - строка подключения к вашей базе данных PostgreSQL.
* EDGE_DRIVER_PATH - путь к драйверу браузера Edge, используемому Selenium.
Пример содержания .env файла:
   ```
    TELEGRAM_BOT_TOKEN=your_token_here
    DATABASE_URL=postgres://username:password@localhost:5432/your_database
    EDGE_DRIVER_PATH=path_to_your_edge_driver

Использование WebDriver
WebDriver используется для выполнения задач, связанных с веб-скрапингом, таких как получение актуального расписания с сайтов. Для корректной работы необходимо установить веб-драйвер для браузера, который вы планируете использовать (например, ChromeDriver или EdgeDriver).

Запуск бота
Для запуска бота выполните:
    python bot.py

Функциональность
Бот поддерживает следующие функции:

Добавление и просмотр пользовательских событий.
Получение расписаний с веб-сайтов.
Автоматическая рассылка напоминаний.