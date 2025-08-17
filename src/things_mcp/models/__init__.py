"""Things 3 data models package."""

# Import from submodules - things_models contains the main models
from .things_models import (
    Todo,
    Project,
    Area,
    Tag,
    Contact,
    TodoResult,
    ProjectResult,
    AreaResult,
    BaseThingsModel,
    ThingsStatus,
    ThingsListType,
    ScheduleOption,
    ThingsList
)

# Import from response_models
from .response_models import (
    AppleScriptResult,
    OperationResult,
    ErrorDetails
)

# Import from parent models.py for backward compatibility if it exists
try:
    from ..models import ServerStats
except ImportError:
    # Define ServerStats here if not available in parent
    from pydantic import BaseModel
    
    class ServerStats(BaseModel):
        """Server statistics."""
        uptime_seconds: float
        total_requests: int
        successful_requests: int
        failed_requests: int
        applescript_executions: int
        cache_hits: int
        cache_size: int

__all__ = [
    'Todo',
    'Project', 
    'Area',
    'Tag',
    'Contact',
    'TodoResult',
    'ProjectResult',
    'AreaResult',
    'ServerStats',
    'BaseThingsModel',
    'ThingsStatus',
    'ThingsListType', 
    'ScheduleOption',
    'ThingsList',
    'AppleScriptResult',
    'OperationResult',
    'ErrorDetails'
]