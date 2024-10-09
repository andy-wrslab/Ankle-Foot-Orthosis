#ifndef POTENTIOMETER_SENSOR_H
#define POTENTIOMETER_SENSOR_H

#include "SensorData.h"
#include "Utilities.h"

class PotentiometerSensor : public Sensor {
public:
    byte channel;

    PotentiometerSensor(byte channelNumber) {
        name = "potentiometer";
        channel = channelNumber;
    }

    void read() override {
        int16_t reading = readADChannel(channel);
        sum += (long)reading;
    }
};

#endif // POTENTIOMETER_SENSOR_H