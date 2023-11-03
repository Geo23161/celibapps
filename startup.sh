#!/bin/bash
python manage.py collectstatic && daphne -b 0.0.0.0 -p 8001 perfectlov.asgi:application
