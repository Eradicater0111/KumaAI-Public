"""KUMA compatibility/test tool registry.

Production registration is authoritative in app.agent.kuma_runtime.create_kuma()
and still passes through KumaAgent.register_tool() + explicit permission metadata.
This mapping exists for integration tests and legacy imports; it is not an
authorization boundary.
"""

from app.tools.system_tools import (
    open_app,
    list_files,
    open_file,
    execute_command,
)
from app.tools.system_monitor import (
    inspect_system,
)

from app.tools.internet_tools import (
    web_search,
    fetch_webpage,
)

from app.tools.location_tools import (
    get_current_location,
)

from app.memory.manager import (
    remember,
    recall,
    forget,
)

from app.tools.computer_tools import (
    screenshot_screen,
    analyze_screen,
    move_mouse,
    move_mouse_vision,
    click_at,
    click_vision,
    type_text,
    press_key,
    scroll,
    hold_mouse,
    hold_mouse_vision,
    release_mouse,
)


KUMA_TOOLS = {

    "open_app": open_app,

    "list_files": list_files,

    "open_file": open_file,

    "inspect_system": inspect_system,

    "get_current_location": get_current_location,

    "web_search": web_search,

    "fetch_webpage": fetch_webpage,

    "remember": remember,

    "recall": recall,

    "forget": forget,

    "execute_command": execute_command,

    "screenshot_screen": screenshot_screen,

    "analyze_screen": analyze_screen,

    "move_mouse": move_mouse,

    "move_mouse_vision": move_mouse_vision,

    "click": click_at,

    "type_text": type_text,

    "press_key": press_key,

    "scroll": scroll,

    "click_vision": click_vision,

    "hold_mouse": hold_mouse,

    "hold_mouse_vision": hold_mouse_vision,

    "release_mouse": release_mouse,

}