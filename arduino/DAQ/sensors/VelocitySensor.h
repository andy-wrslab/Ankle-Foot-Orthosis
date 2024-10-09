#ifndef VELOCITY_SENSOR_H
#define VELOCITY_SENSOR_H

#include "SensorData.h"

class VelocitySensor : public Sensor {
public:
  volatile int16_t* pot_reading_prev;
  volatile int16_t* pot_reading_curr;

  VelocitySensor(volatile int16_t* prev, volatile int16_t* curr) {
    name = "velocity";
    pot_reading_prev = prev;
    pot_reading_curr = curr;
  }

  void read() override {
    sum += (long)(*pot_reading_curr - *pot_reading_prev) / 0.2 / 1000;
  }
};

#endif // VELOCITY_SENSOR_H