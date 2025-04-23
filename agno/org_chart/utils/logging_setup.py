import sys
import logging


def setup_logging(level=logging.INFO, stream=False):
    """Configures root logger."""
    stdout = sys.stdout if stream else False

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=stdout,
    )

    # Quieten noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    print(f"Logging configured with level: {logging.getLevelName(level)}")
