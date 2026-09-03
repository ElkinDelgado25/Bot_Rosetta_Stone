from Resolucion_script_rosseta.infraestructura.infra_logging import get_logger


class LoggingMixin:
    """Mixin que proporciona funcionalidad de logging a las clases."""

    def __init__(self):
        self._logger = get_logger(self.__class__.__name__)

    @property
    def logger(self):
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger

    # Convenience methods for common logging operations
    def debug(self, message, *args, **kwargs):
        """Log a debug message."""
        self.logger.info(message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        """Log an info message."""
        self.logger.info(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """Log a warning message."""
        self.logger.warning(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """Log an error message."""
        self.logger.error(message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """Log a critical message."""
        self.logger.critical(message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        """Log an exception message with stack trace."""
        self.logger.exception(message, *args, **kwargs)

