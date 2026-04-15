# Tourist Audio Guide - Django API Server

Welcome to the backend API server for the Tourist Audio Guide project. The application is built using Django and Django REST Framework, and connected to a MySQL database.

## Prerequisites
1. **Python 3.10+**
2. **MySQL Server** installed and running on your local machine.

## 1. Setting Up the Database
Before running the Django app, you must ensure that your MySQL server is running and the credentials in your `.env` file are correct.

1. Open your MySQL client (like MySQL Workbench, DBeaver, or command line).
2. Create the database specified in your `.env`. For example:
   ```sql
   CREATE DATABASE gps_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
3. Check your `.env` file credentials. If you encountered an `Access denied for user 'root'@'localhost'` error, you need to ensure the `DB_PASSWORD` value in `.env` matches your actual local MySQL root password.

## 2. Setting Up the Python Environment
Open a terminal in the project root (`gps_server`) and activate the virtual environment:

**Windows (PowerShell):**
```bash
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```bash
.\venv\Scripts\activate.bat
```

*(You will see a `(venv)` prefix in your terminal prompt when activated).*

## 3. Setup .env file

Create a .env file in the project root (`gps_server`) directory:

```bash
DJANGO_SECRET_KEY=dev-only-secret-key
DEBUG=1
ALLOWED_HOSTS=*

DB_NAME=gps_db
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_HOST=localhost
DB_PORT=3306

ACCESS_TOKEN_MINUTES=30
REFRESH_TOKEN_DAYS=14
TIME_ZONE=Asia/Ho_Chi_Minh
```

## 4. Creating Database Migrations
If you see an error like `ValueError: Dependency on app with no migrations` when trying to migrate, it's because you need to generate the migration files for the custom apps first!

Run the following commands in order:
```bash
python manage.py makemigrations
python manage.py migrate
```

- `makemigrations` looks at the Python code (models.py) and generates the blueprint for the database tables.
- `migrate` actually connects to MySQL and creates those tables.

## 5. Running the Development Server
Once migrations have successfully applied to your MySQL database, start the API server:

```bash
python manage.py runserver
```

## 6. View the API Documentation (Swagger)
We use `drf-spectacular` to automatically generate beautiful Swagger UI documentation for our API endpoints.

While the server is running, open your web browser and go to:
👉 **[http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)**

From here, you will be able to test all of the endpoints (Authentication, POIs, Tours, Subscriptions) directly from the browser!
