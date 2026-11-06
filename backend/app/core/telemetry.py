"""Small structured logger: only explicit metadata, never prompts or credentials."""
import json
import logging
from datetime import datetime, timezone


class EventFormatter(logging.Formatter):
    def format(self, record):
        event = {"time": datetime.now(timezone.utc).isoformat(), "level": record.levelname, "event": record.getMessage()}
        for name in ('request_id','method','status','latency_ms','input_tokens','output_tokens'):
            if hasattr(record,name):
                event[name] = getattr(record,name)
        return json.dumps(event)


def event_logger(name):
    parent = logging.getLogger('study_mate')
    if not parent.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(EventFormatter())
        parent.addHandler(handler)
        parent.setLevel(logging.INFO)
        parent.propagate = False
    return logging.getLogger('study_mate.' + name)
