#pragma once

// Boot screen header shows the real firmware version so the panel matches
// the WebUI device info and the OTA channel.
#ifdef FW_VERSION
#define WS43B_DISPLAY_VERSION FW_VERSION
#else
#define WS43B_DISPLAY_VERSION "dev"
#endif
