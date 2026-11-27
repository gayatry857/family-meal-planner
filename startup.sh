#!/bin/sh
# Startup command for Azure App Service (Linux, Python).
# In the portal, put "startup.sh" in the Startup Command box.
#
# PORT is supplied by App Service; 8000 is the fallback for local use.
# uvicorn_worker replaces uvicorn.workers, deprecated since uvicorn 0.30.
exec gunicorn app.main:app --bind=0.0.0.0:${PORT:-8000} --worker-class uvicorn_worker.UvicornWorker --workers 2 --timeout 600 --access-logfile - --error-logfile -
