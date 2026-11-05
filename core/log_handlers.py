"""Logging handlers. Kept free of model imports: logging is set up before apps load."""
import logging


class ThreatLogHandler(logging.Handler):
    def emit(self, record):
        try:
            from .security import record_from_log
            record_from_log(record)
        except Exception:  # a log handler must never break the request it reports on
            self.handleError(record)
