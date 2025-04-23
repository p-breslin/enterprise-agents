import sys
import logging


class AbortOnLogHandler(logging.Handler):
    """
    Raises RuntimeError the moment a log record at or above `min_level` is emitted.
    """

    def __init__(self, min_level=logging.ERROR):
        super().__init__(level=min_level)
        self.min_level = min_level

    def emit(self, record):
        if record.levelno >= self.min_level:
            # Flush existing handlers so the last message isn’t lost
            for h in logging.getLogger().handlers:
                h.flush()
            raise RuntimeError(
                f"Abort on log record: {record.levelname} – {record.getMessage()}"
            )


def setup_logging(
    level: int = logging.INFO,
    stream=None,
    abort_on_log: bool = False,
    abort_level: int = logging.ERROR,
) -> None:
    """
    Configures the root logger.

    Args:
        level: default overall log level (INFO by default)
        stream: if truthy, log to sys.stdout; otherwise caller adds own handlers
        abort_on_log: if True, install AbortOnLogHandler to raise errors
        abort_level: the threshold for aborting (ERROR by default)
    """
    stdout = sys.stdout if stream else None

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=stdout,
    )

    # Quieten noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Optionally “fail fast” on logged problems
    if abort_on_log:
        root = logging.getLogger()

        # Avoid double-adding if setup_logging() is called twice
        if not any(isinstance(h, AbortOnLogHandler) for h in root.handlers):
            root.addHandler(AbortOnLogHandler(min_level=abort_level))

    print(f"Logging configured with level: {logging.getLevelName(level)}")
