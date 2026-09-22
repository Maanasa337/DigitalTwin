"""`python -m edge`: run the edge runner with settings from EDGE_* environment variables."""

import logging
import sys

from edge.config import EdgeConfig
from edge.runner import EdgeRunner


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("paho").setLevel(logging.WARNING)
    config = EdgeConfig.from_env()
    if not config.assets:
        logging.error("EDGE_ASSETS is empty; nothing to run")
        return 2
    EdgeRunner(config).run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
