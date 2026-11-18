"""Entry point: python main.py"""
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

import customtkinter as ctk

import config as C
from ui import App


def setup_logging() -> None:
    # Rotating: app.log never grows past ~1 MB (keeps 2 old files).
    handlers = [RotatingFileHandler(C.LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")]
    if sys.stderr is not None:  # a --windowed .exe has no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s",
        handlers=handlers,
    )
    # Crashes outside Tk callbacks (main thread or worker threads) go to the log too.
    sys.excepthook = lambda *exc: logging.critical("uncaught error", exc_info=exc)
    threading.excepthook = lambda a: logging.critical(
        "uncaught error in %s", a.thread.name if a.thread else "?",
        exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def selftest() -> int:
    """`ContineoAutoLogin.exe --selftest`: check the parts that most often
    break after packaging. Results go to app.log (a windowed exe has no console)."""
    log = logging.getLogger("selftest")
    ok = True
    log.info("frozen=%s data dir=%s", getattr(sys, "frozen", False), C.APP_DIR)
    try:
        import keyring
        import storage  # noqa: F401  (selects the Windows backend)
        log.info("keyring backend: %s", keyring.get_keyring())
        log.info("users found: %d", len(storage.list_users()))
    except Exception:
        log.exception("keyring/storage FAILED"); ok = False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:  # starts the bundled Node driver
            b = p.chromium.launch(channel="chrome", headless=True)  # finds installed Chrome
            log.info("Chrome found: version %s", b.version)
            b.close()
    except Exception:
        log.exception("playwright/Chrome FAILED"); ok = False
    log.info("SELFTEST %s", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def main() -> None:
    setup_logging()
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    ctk.set_appearance_mode("system")      # follows Windows light/dark
    ctk.set_default_color_theme("blue")
    App().mainloop()


if __name__ == "__main__":
    main()
