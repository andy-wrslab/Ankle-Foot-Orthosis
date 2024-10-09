#ifndef FSR_SENSOR_H
#define FSR_SENSOR_H

#include "SensorData.h"
#include "../utilities/Utilities.h"

class FsrSensor : public Sensor {
public:
  FsrSensor() {
    name = "fsr";
  }

  void read() override {
    sum += (long)(get_pressure(3) + get_pressure(4));
  }
};

#endif // FSR_SENSOR_H