#include "Timer.h"

// Variables used in the timer functions
volatile uint16_t ADC_cycles = 0;
volatile int16_t pot_reading_prev = 0;
volatile int16_t pot_reading_curr = 0;

extern volatile int16_t CH_NUM_LC_1; // Add extern declaration if not already present

void functionADCTimer() {
    pot_reading_prev = pot_reading_curr;
    pot_reading_curr = readADChannel(CH_NUM_LC_1);

    // Read all sensors
    for (int i = 0; i < numSensors; i++) {
        sensors[i]->read();
    }

    ADC_cycles++;

    if (ADC_cycles == PNTS_TO_AVG) {
        for (int i = 0; i < numSensors; i++) {
            sensors[i]->raw = ((double)(sensors[i]->sum)) / PNTS_TO_AVG;

            // Assign processed values
            noInterrupts();
            sensors[i]->local = sensors[i]->raw;
            interrupts();

            // Reset sum
            sensors[i]->sum = 0;
        }

        ADC_cycles = 0;
    }
}

// `functionFilterTimer` remains unchanged