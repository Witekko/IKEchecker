#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# Zbiera pliki CSS/JS do jednego folderu
python manage.py collectstatic --no-input

# Aktualizuje bazę danych
python manage.py migrate