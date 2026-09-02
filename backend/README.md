# Delivery Scanner Backend

FastAPI + PostgreSQL API for the Delivery Scanner phone and desktop apps.

Set DATABASE_URL to your hosted PostgreSQL connection string, then run:

uvicorn main:app --host 0.0.0.0 --port 8000

Create the table first using schema.sql.
