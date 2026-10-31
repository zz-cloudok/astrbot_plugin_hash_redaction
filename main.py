import re
from sys import maxsize

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import CustomFilter
from astrbot.api.message_components import At, Plain, Reply
from astrbot.api.star import Context, Star


DEFAULT_CONFIG = {
    "enabled": True,
}


def _make_pattern(delimiter: str) -> re.Pattern[str]:
    token = re.escape(delimiter)
    double = re.escape(delimiter * 2)
    return re.compile(
        rf"{double}.*?{double}|{token}.*?{token}",
        re.DOTALL,
    )


class HashRedactionFilter(CustomFilter):
    """Wake only when a complete hidden block exists."""

    def filter(self, event: AstrMessageEvent, cfg) -> bool:
        return bool(_make_pattern("#").search(event.message_str or ""))


class HashRedactionPlugin(Star):
    """Remove hash-delimited text before other plugins or the LLM see it."""

    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context)
        self.plugin_config = config or {}

    @filter.custom_filter(HashRedactionFilter, priority=maxsize)
    async def redact_hash_blocks(self, event: AstrMessageEvent) -> None:
        if not bool(self.plugin_config.get("enabled", True)):
            return

        pattern = _make_pattern("#")
        visible_text = pattern.sub("", event.message_str or "")
        visible_text = re.sub(r"[ \t]{2,}", " ", visible_text).strip()

        new_components = []
        visible_non_text = False
        for component in event.get_messages():
            if isinstance(component, Plain):
                cleaned = pattern.sub("", component.text)
                if cleaned.strip():
                    new_components.append(Plain(cleaned))
            elif not isinstance(component, (At, Reply)):
                visible_non_text = True
                new_components.append(component)
            else:
                new_components.append(component)

        event.message_obj.message = new_components
        event.message_obj.message_str = visible_text
        event.message_str = visible_text

        if not visible_text and not visible_non_text:
            event.set_extra("_hash_block_suppressed", True)
            event.stop_event()
            self.logger.info(
                "Suppressed hash-only message for %s",
                event.unified_msg_origin,
            )
            return

        event.set_extra("_hash_blocks_redacted", True)
        self.logger.info(
            "Removed hidden hash block(s) before processing %s",
            event.unified_msg_origin,
        )
