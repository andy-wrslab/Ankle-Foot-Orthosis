#ifndef SENSOR_DATA_H
#define SENSOR_DATA_H

#include <Arduino.h> // Ensure this is included only once

class Sensor {
public:
    String name; // Add this line
    double raw = 0.0;
    double filtered = 0.0;
    double local = 0.0;
    volatile double buffer_raw[4] = {0.0};
    volatile double buffer_filt[4] = {0.0};
    volatile long sum = 0;

    // Virtual function to read sensor data
    virtual void read() = 0; // Pure virtual function
};

#endif // SENSOR_DATA_H