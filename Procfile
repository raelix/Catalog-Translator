web: gunicorn main:app -k uvicorn.workers.UvicornWorker --workers 1 --preload --threads 2 --timeout 120 --bind 0.0.0.0:$PORT
