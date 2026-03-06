"""Shared Logger instance for the restaurant-booking service.

Import from here rather than constructing Logger directly in each module.
Powertools re-uses the same instance when the service name matches, but
having a single canonical source prevents accidental divergence in service
names or sampling rates.
"""

import logging
import re

from aws_lambda_powertools import Logger


class _PiiRedactionFilter(logging.Filter):
    """Mask emails and phone numbers from log records before CloudWatch emission.

    Covers the Powertools logger (structured JSON) and the root Python logger
    (Strands internal logs). Lightweight regex — no ML models in the hot path.
    Bedrock Guardrails handles PII masking at the model I/O layer; this filter
    catches anything that leaks into exception messages or tool-call logs.
    """

    _EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.]+")
    _PHONE = re.compile(r"(\+?1[\s.\-]?)?(\(?\d{3}\)?[\s.\-]?)?\d{3}[\s.\-]?\d{4}")

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._scrub(str(record.msg))
        if record.args:
            record.args = tuple(self._scrub(str(a)) for a in record.args)
        return True

    def _scrub(self, text: str) -> str:
        text = self._EMAIL.sub("[EMAIL]", text)
        text = self._PHONE.sub("[PHONE]", text)
        return text


_pii_filter = _PiiRedactionFilter()

logger = Logger(service="restaurant-booking")
# Apply to the Powertools logger (covers all structured log output)
logger.addFilter(_pii_filter)
# Apply to the root logger so Strands internal log lines are also scrubbed
logging.getLogger().addFilter(_pii_filter)
