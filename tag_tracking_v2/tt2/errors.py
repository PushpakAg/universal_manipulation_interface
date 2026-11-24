"""
Exception types. Each carries what failed and what to do about it, so a log line
or a summary row is enough to act on. Scripts raise these instead of bare asserts
(asserts are removed under python -O and give no context).
"""


class PipelineError(Exception):
    """A pipeline step or batch stage failed. `step` names it, `log_path` points to the full output."""

    def __init__(self, message: str, step: str = None, log_path=None):
        super().__init__(message)
        self.step = step
        self.log_path = None if log_path is None else str(log_path)

    def __str__(self):
        text = super().__str__()
        parts = [text]
        if self.step:
            parts.insert(0, f"[{self.step}]")
        if self.log_path:
            parts.append(f"(log: {self.log_path})")
        return ' '.join(parts)


class InputError(PipelineError):
    """The input is missing or malformed (file not found, bad option value, wrong layout)."""


class ConfigError(PipelineError):
    """The configuration is inconsistent with the data (unknown camera serial, missing section)."""


class StepTimeout(PipelineError):
    """A child process exceeded its time limit and was terminated."""


class TransferError(PipelineError):
    """An S3 download or upload failed or could not be verified."""


class ExportError(PipelineError):
    """Writing an output file failed. The partial output was removed."""


def require(condition, message: str, error=InputError, **kw):
    """Raise `error(message)` if condition is false. Replacement for `assert` on external input."""
    if not condition:
        raise error(message, **kw)
