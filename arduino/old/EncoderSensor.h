#ifndef ENCODER_SENSOR_H
#define ENCODER_SENSOR_H

#include "SensorData.h"
#include "Utilities.h"

class EncoderSensor : public Sensor {
public:
    double* encoder_current;

    EncoderSensor(double* current) {
        name = "encoder";
        encoder_current = current;
    }

    void read() override {
        sum += (long)(*encoder_current);
    }
};

#endif // ENCODER_SENSOR_H