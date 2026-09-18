"""
Logging Configuration für APA_from_CAD.

Verwendet structlog für strukturierte JSON-Logs mit Context-Informationen.
Ersetzt print()-Statements durch logger-Calls.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog
from structlog.types import Processor


def configure_logging(
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    json_logs: bool = False,
) -> None:
    """
    Konfiguriere structlog für das gesamte Projekt.
    
    Args:
        log_level: Logging Level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
        json_logs: If True, output JSON logs; else, colored console output
    
    Example:
        >>> configure_logging(log_level="DEBUG", json_logs=False)
        >>> logger = structlog.get_logger()
        >>> logger.info("workflow_started", assembly="IPA_Cranfield")
    """
    # Timestamp processor
    timestamper = structlog.processors.TimeStamper(fmt="iso")
    
    # Shared processors
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.ExtraAdder(),
        timestamper,
    ]
    
    if json_logs:
        # JSON output für Production
        structlog.configure(
            processors=shared_processors
            + [
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    else:
        # Colored console output für Development
        structlog.configure(
            processors=shared_processors
            + [
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
        )
    
    # Configure stdlib logging
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())
    
    # Optional file handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """
    Get a configured structlog logger.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Configured structlog BoundLogger
        
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("processing_assembly", assembly="IPA_Cranfield", parts=15)
    """
    return structlog.get_logger(name)


# Configure default logging on module import
configure_logging(
    log_level="INFO",
    json_logs=False,  # Colored console for development
)
