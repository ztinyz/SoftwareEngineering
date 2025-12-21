# Clinica — Django website for a Romanian clinic

## Description

**Clinica** is a Django-based web application implementing the website for a Romanian medical clinic. It provides the necessary backend and frontend components to manage clinic operations via a web interface.

## Features

- Web UI built with Django (HTML, CSS/SCSS, JavaScript) for clinic operations.  
- User authentication and login system.  
- Modular structure suitable for extension: contains separate modules (e.g. `login`, `index`, and the Django project root).  
- SQLite database backend (default `db.sqlite3`), for easy setup and development.  
- Simple, straightforward setup ideal for small-to-medium clinics or for demonstration/learning purposes.

## Requirements

- Python 3.x  
- Django (version compatible with the project)  
- A modern web browser  
- (Optional) Virtual environment for isolation

## Installation & Setup

git clone https://github.com/ztinyz/Clinica.git
cd Clinica
python -m venv venv
source venv/bin/activate        # or `venv\\Scripts\\activate` on Windows
pip install -r requirements.txt # or install Django manually if no requirements file
python manage.py migrate
python manage.py runserver
After this, open your browser at http://127.0.0.1:8000/ to access the website.

## Usage

Use the login page to authenticate and access protected pages.

Modify or extend the Django apps (login, index, others) to suit your clinic’s needs (e.g. patient records, scheduling, etc.).

The default database is SQLite for ease of development; for production usage, consider switching to a more robust database (PostgreSQL, MySQL, etc.) and updating Django settings accordingly.

## Project Structure

Clinica/            # Django project directory  
  ├── login/        # Login app (authentication)  
  ├── index/        # Main site/app  
  ├── manage.py  
  ├── db.sqlite3    # Default SQLite database (auto-generated)  
  └── …             # Other standard Django project files and settings  
