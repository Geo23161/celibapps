#!/bin/bash
python manage.py collectstatic && daphne perfectlov.asgi:application
