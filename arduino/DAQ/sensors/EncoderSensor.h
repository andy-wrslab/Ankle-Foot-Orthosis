#ifndef ENCODER_SENSOR_H
#define ENCODER_SENSOR_H

#include "SensorData.h"
#include "../utilities/Utilities.h"

class EncoderSensor : public Sensor {
public:

  EncoderSensor() {
    name = "encoder";
  }

  void read() override {
    sum += (long)readRegister();
  }
};

#endif // ENCODER_SENSOR_H