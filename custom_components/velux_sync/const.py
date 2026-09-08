"""Constants for the Velux Sync integration."""

from homeassistant.const import Platform

DOMAIN = "velux_sync"
DOMAIN_TITLE = "Velux Sync"

CONF_WINDOW_ENTITY = "window_entity"
CONF_STORE_ENTITY = "store_entity"

DEFAULT_TIMEOUT = 120

PLATFORMS = [Platform.COVER]