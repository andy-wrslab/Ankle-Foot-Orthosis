#include "Timer.h"

volatile uint16_t ADC_cycles = 0;
volatile int16_t pot_reading_prev = 0;
volatile int16_t pot_reading_curr = 0;

extern const byte CH_NUM_LC_1;
extern Sensor* sensors[];
extern int numSensors;

// Variables
const uint16_t PNTS_TO_AVG = 5;                // Average points to read

// Add filter coefficients here
// Filter coefficients - Butterworth, 2nd order, 12 Hz passband
const double a_lc[] = {1.0, -1.911197067426073, 0.914975834801433};
const double b_lc[] = {0.0009446918438401619, 0.001889383687680, 0.0009446918438401619};

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

void functionFilterTimer() {
  for (int var = 0; var < numSensors; var++) {
    noInterrupts();
    sensors[var]->filtered = b_lc[0] * sensors[var]->local;
    interrupts();

    for (int i = 1; i < 3; i++) {
      sensors[var]->filtered += b_lc[i] * sensors[var]->buffer_raw[i - 1]
                              - a_lc[i] * sensors[var]->buffer_filt[i - 1];
    }

    for (int i = 3; i > 0; i--) {
      sensors[var]->buffer_raw[i] = sensors[var]->buffer_raw[i - 1];
      sensors[var]->buffer_filt[i] = sensors[var]->buffer_filt[i - 1];
    }

    sensors[var]->buffer_raw[0] = sensors[var]->local;
    sensors[var]->buffer_filt[0] = sensors[var]->filtered;
  }
}