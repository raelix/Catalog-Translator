web: gunicorn main:app -k uvicorn.workers.UvicornWorker --workers 1 --preload --timeout 0 --bind 0.0.0.0:$PORT
