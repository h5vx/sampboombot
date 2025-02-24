import logging
import logging.config

from dynaconf import Dynaconf

settings = Dynaconf(
    envvar_prefix="BOOMBOT",
    settings_files=['settings.yaml', '.secrets.yaml'],
)

logging.config.dictConfig(settings.logging)
