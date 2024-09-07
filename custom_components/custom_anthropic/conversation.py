"""Conversation support for Custom Anthropic."""

from collections.abc import Callable
import json
import logging
import os
from datetime import datetime
from typing import Any, Literal, cast

import anthropic
from anthropic._types import NOT_GIVEN
from anthropic.types import (
    Message,
    MessageParam,
    TextBlock,
    TextBlockParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlock,
    ToolUseBlockParam,
)
import voluptuous as vol
from voluptuous_openapi import convert

from homeassistant.components import conversation
from homeassistant.components.conversation import trace
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LLM_HASS_API, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers import device_registry as dr, intent, llm, template
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import ulid

from . import AnthropicConfigEntry
from .const import (
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_PROMPT,
    CONF_TEMPERATURE,
    DOMAIN,
    LOGGER,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
    CONF_LOG_LEVEL,
    CONF_LOG_FILE,
)

MAX_TOOL_ITERATIONS = 10

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: AnthropicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Custom Anthropic conversation entities."""
    agent = CustomAnthropicConversationEntity(config_entry)
    async_add_entities([agent])

def _format_tool(
    tool: llm.Tool, custom_serializer: Callable[[Any], Any] | None
) -> ToolParam:
    """Format tool specification."""
    return ToolParam(
        name=tool.name,
        description=tool.description or "",
        input_schema=convert(tool.parameters, custom_serializer=custom_serializer),
    )

def _message_convert(
    message: Message,
) -> MessageParam:
    """Convert from class to TypedDict."""
    param_content: list[TextBlockParam | ToolUseBlockParam] = []

    for message_content in message.content:
        if isinstance(message_content, TextBlock):
            param_content.append(TextBlockParam(type="text", text=message_content.text))
        elif isinstance(message_content, ToolUseBlock):
            param_content.append(
                ToolUseBlockParam(
                    type="tool_use",
                    id=message_content.id,
                    name=message_content.name,
                    input=message_content.input,
                )
            )

    return MessageParam(role=message.role, content=param_content)

class CustomAnthropicConversationEntity(
    conversation.ConversationEntity, conversation.AbstractConversationAgent
):
    """Custom Anthropic conversation agent."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: AnthropicConfigEntry) -> None:
        """Initialize the agent."""
        self.entry = entry
        self.history: dict[str, list[MessageParam]] = {}
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Custom Anthropic",
            model="Custom Claude",
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        if self.entry.options.get(CONF_LLM_HASS_API):
            self._attr_supported_features = (
                conversation.ConversationEntityFeature.CONTROL
            )
        
        # Set up logging
        log_level = getattr(logging, entry.options.get(CONF_LOG_LEVEL, "INFO").upper())
        log_file = entry.options.get(CONF_LOG_FILE, "custom_anthropic_logs.txt")
        self.logger = logging.getLogger(f"{__name__}.{entry.entry_id}")
        self.logger.setLevel(log_level)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(file_handler)

        # Set up custom logging for raw API input/output
        self.raw_log_file = entry.options.get(CONF_LOG_FILE, "custom_anthropic_raw_logs.txt")
        self.raw_log_file = os.path.join(self.hass.config.config_dir, self.raw_log_file)

    def log_raw_io(self, input_data: str, output_data: str) -> None:
        """Log raw input and output to a dedicated file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.raw_log_file, "a") as f:
            f.write(f"--- {timestamp} ---\n")
            f.write(f"Input:\n{input_data}\n\n")
            f.write(f"Output:\n{output_data}\n\n")
            f.write("-" * 50 + "\n\n")

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return a list of supported languages."""
        return MATCH_ALL

    @property
    def agent_id(self) -> str:
        """Return the agent ID."""
        return f"{DOMAIN}_{self.entry.entry_id}"

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a sentence."""
        options = self.entry.options
        intent_response = intent.IntentResponse(language=user_input.language)
        llm_api: llm.APIInstance | None = None
        tools: list[ToolParam] | None = None
        user_name: str | None = None
        llm_context = llm.LLMContext(
            platform=DOMAIN,
            context=user_input.context,
            user_prompt=user_input.text,
            language=user_input.language,
            assistant=conversation.DOMAIN,
            device_id=user_input.device_id,
        )

        if options.get(CONF_LLM_HASS_API):
            try:
                llm_api = await llm.async_get_api(
                    self.hass,
                    options[CONF_LLM_HASS_API],
                    llm_context,
                )
            except HomeAssistantError as err:
                LOGGER.error("Error getting LLM API: %s", err)
                intent_response.async_set_error(
                    intent.IntentResponseErrorCode.UNKNOWN,
                    f"Error preparing LLM API: {err}",
                )
                return conversation.ConversationResult(
                    response=intent_response, conversation_id=user_input.conversation_id
                )
            tools = [
                _format_tool(tool, llm_api.custom_serializer) for tool in llm_api.tools
            ]

        if user_input.conversation_id is None:
            conversation_id = ulid.ulid_now()
            messages = []
        elif user_input.conversation_id in self.history:
            conversation_id = user_input.conversation_id
            messages = self.history[conversation_id]
        else:
            try:
                ulid.ulid_to_bytes(user_input.conversation_id)
                conversation_id = ulid.ulid_now()
            except ValueError:
                conversation_id = user_input.conversation_id
            messages = []

        if (
            user_input.context
            and user_input.context.user_id
            and (
                user := await self.hass.auth.async_get_user(user_input.context.user_id)
            )
        ):
            user_name = user.name

        try:
            prompt_parts = [
                template.Template(
                    llm.BASE_PROMPT
                    + options.get(CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT),
                    self.hass,
                ).async_render(
                    {
                        "ha_name": self.hass.config.location_name,
                        "user_name": user_name,
                        "llm_context": llm_context,
                    },
                    parse_result=False,
                )
            ]

        except TemplateError as err:
            LOGGER.error("Error rendering prompt: %s", err)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Sorry, I had a problem with my template: {err}",
            )
            return conversation.ConversationResult(
                response=intent_response, conversation_id=conversation_id
            )

        if llm_api:
            prompt_parts.append(llm_api.api_prompt)

        prompt = "\n".join(prompt_parts)

        messages = [*messages, MessageParam(role="user", content=user_input.text)]

        self.logger.debug("Prompt: %s", messages)
        self.logger.debug("Tools: %s", tools)
        trace.async_conversation_trace_append(
            trace.ConversationTraceEventType.AGENT_DETAIL,
            {"system": prompt, "messages": messages},
        )

        client = self.entry.runtime_data

        for _iteration in range(MAX_TOOL_ITERATIONS):
            try:
                response = await client.messages.create(
                    model=options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL),
                    messages=messages,
                    tools=tools or NOT_GIVEN,
                    max_tokens=options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS),
                    system=prompt,
                    temperature=options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
                )

                # Log raw input and output
                self.log_raw_io(
                    json.dumps({"messages": messages, "tools": tools, "system": prompt}, indent=2),
                    json.dumps(response.model_dump(), indent=2)
                )

            except anthropic.AnthropicError as err:
                intent_response.async_set_error(
                    intent.IntentResponseErrorCode.UNKNOWN,
                    f"Sorry, I had a problem talking to Anthropic: {err}",
                )
                return conversation.ConversationResult(
                    response=intent_response, conversation_id=conversation_id
                )

            self.logger.info("Raw API Response: %s", response)

            messages.append(_message_convert(response))

            if response.stop_reason != "tool_use" or not llm_api:
                break

            tool_results: list[ToolResultBlockParam] = []
            for tool_call in response.content:
                if isinstance(tool_call, TextBlock):
                    self.logger.info(tool_call.text)

                if not isinstance(tool_call, ToolUseBlock):
                    continue

                tool_input = llm.ToolInput(
                    tool_name=tool_call.name,
                    tool_args=cast(dict[str, Any], tool_call.input),
                )
                self.logger.debug("Tool call: %s(%s)", tool_input.tool_name, tool_input.tool_args)

                try:
                    tool_response = await llm_api.async_call_tool(tool_input)
                except (HomeAssistantError, vol.Invalid) as e:
                    tool_response = {"error": type(e).__name__}
                    if str(e):
                        tool_response["error_text"] = str(e)

                self.logger.debug("Tool response: %s", tool_response)
                tool_results.append(
                    ToolResultBlockParam(
                        type="tool_result",
                        tool_use_id=tool_call.id,
                        content=json.dumps(tool_response),
                    )
                )

            messages.append(MessageParam(role="user", content=tool_results))

        self.history[conversation_id] = messages

        for content in response.content:
            if isinstance(content, TextBlock):
                intent_response.async_set_speech(content.text)
                break

        return conversation.ConversationResult(
            response=intent_response, conversation_id=conversation_id
        )

    async def async_added_to_hass(self) -> None:
        """When entity is added to Home Assistant."""
        await super().async_added_to_hass()
        self.entry.async_on_unload(
            self.entry.add_update_listener(self._async_entry_update_listener)
        )

    async def _async_entry_update_listener(
        self, hass: HomeAssistant, entry: ConfigEntry
    ) -> None:
        """Handle options update."""
        await hass.config_entries.async_reload(entry.entry_id)

    async def async_get_agent_info(self) -> conversation.AgentInfo:
        """Get information about the agent."""
        return conversation.AgentInfo(
            name="Custom Claude",
            id=self.agent_id,
        )