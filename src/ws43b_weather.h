#pragma once
#include "config.h"
#if defined(BOARD_IS_WS43B)
#include "ws43b_weather_data.h"
void loadWs43bWeather();
bool ws43bSetupDone();
bool finishWs43bSetup(bool skip, bool dark);
void tickWs43bWeather();
ws43b_weather::Config ws43bWeatherConfig();
ws43b_weather::Data ws43bWeatherData();
bool saveWs43bWeather(ws43b_weather::Config value);
bool ws43bSolarNight(bool &night);
const char *ws43bWeatherDescription(int code);
#endif
