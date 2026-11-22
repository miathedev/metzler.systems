"""Vulture-Whitelist: FastAPI-Routen werden nur ueber @app.get(...) am Decorator
registriert, vulture sieht den Namen nicht als "benutzt".

Aufruf: vulture app whitelist_vulture.py
"""

import main  # noqa: F401

main.api_health
main.api_trigger
main.api_status_root
main.api_status
