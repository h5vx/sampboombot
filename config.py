from dynaconf import Dynaconf

settings = Dynaconf(
    envvar_prefix="BOOMBOT",
    settings_files=['settings.yaml', '.secrets.yaml'],
)