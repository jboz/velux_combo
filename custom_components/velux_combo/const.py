"""Constants for the Velux Combo integration."""

from homeassistant.const import Platform

DOMAIN = "velux_combo"
DOMAIN_TITLE = "Velux Combo"

CONF_WINDOW_ENTITY = "window_entity"
CONF_STORE_ENTITY = "store_entity"

DEFAULT_TIMEOUT = 120

PLATFORMS = [Platform.COVER]