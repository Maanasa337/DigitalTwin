"""Entrypoint for the ingest consumer: ``python -m app.ingest``."""

import logging
import sys

from app.core.observability import configure_logging
from app.ingest.consumer import IngestConsumer


def main() -> int:
    configure_logging("INFO")
    logging.getLogger("paho").setLevel(logging.WARNING)
    consumer = IngestConsumer()
    consumer.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
