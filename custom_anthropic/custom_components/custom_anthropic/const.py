"""Constants for the Custom Anthropic integration."""

import logging

DOMAIN = "custom_anthropic"
LOGGER = logging.getLogger(__package__)

CONF_RECOMMENDED = "recommended"
CONF_PROMPT = "prompt"
CONF_CHAT_MODEL = "chat_model"
RECOMMENDED_CHAT_MODEL = "claude-3-haiku-20240307"
CONF_MAX_TOKENS = "max_tokens"
RECOMMENDED_MAX_TOKENS = 1024
CONF_TEMPERATURE = "temperature"
RECOMMENDED_TEMPERATURE = 1.0

# New constants for logging raw input and output
CONF_LOG_LEVEL = "log_level"
CONF_LOG_FILE = "log_file"
DEFAULT_LOG_LEVEL = "info"
DEFAULT_LOG_FILE = "custom_anthropic_logs.txt"