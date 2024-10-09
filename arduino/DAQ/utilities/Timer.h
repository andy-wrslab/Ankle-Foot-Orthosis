#ifndef TIMER_H
#define TIMER_H

#include <Arduino.h>
#include "../sensors/SensorData.h"
#include "Utilities.h"

// Externally declared variables
extern Sensor* sensors[];
extern int numSensors;

extern const double a_lc[];
extern const double b_lc[];
extern const uint16_t PNTS_TO_AVG;

extern volatile int16_t pot_reading_prev;
extern volatile int16_t pot_reading_curr;
extern volatile uint16_t ADC_cycles;
extern double encoder_current;

void functionADCTimer();
void functionFilterTimer();

#endif // TIMER_H