"""Constants for the EGD Distribuce integration."""

DOMAIN = "egddistribuce"

# Configuration keys
CONF_PSC = "psc"
CONF_CODE_A = "code_a"
CONF_CODE_B = "code_b"
CONF_CODE_DP = "code_dp"
CONF_HDO_CODE = "hdo_code"  # For multiple HDO codes (405, 406, 410)
CONF_PRICE_NT = "price_nt"
CONF_PRICE_VT = "price_vt"
CONF_CONFIG_TYPE = "config_type"  # Type of configuration

# Configuration types
CONFIG_TYPE_CLASSIC = "classic"  # Classic A+B+DP
CONFIG_TYPE_HDO_CODES = "hdo_codes"  # Multiple HDO codes
CONFIG_TYPE_SMART = "smart"  # Smart meter

# Default values
DEFAULT_PRICE_NT = 1.0
DEFAULT_PRICE_VT = 2.0
DEFAULT_NAME = "EGD HDO"

# Update interval
UPDATE_INTERVAL = 300  # seconds
