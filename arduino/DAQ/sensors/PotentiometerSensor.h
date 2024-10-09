#ifndef POTENTIOMETER_SENSOR_H
#define POTENTIOMETER_SENSOR_H

#include "SensorData.h"
#include "../utilities/Utilities.h"

// ADC channels
const byte CH_NUM_LC_1 = 1;

class PotentiometerSensor : public Sensor {
public:
  PotentiometerSensor() {
    name = "potentiometer";
  }

  void read() override {
    sum += (long)readADChannel(CH_NUM_LC_1);
  }
};

#endif // POTENTIOMETER_SENSOR_H