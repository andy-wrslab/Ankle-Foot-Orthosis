#ifndef UTILITIES_H
#define UTILITIES_H

#include <Arduino.h>

// Define ADC Pins
const uint16_t CONVST = 38;
const uint16_t SCLK = 37;
const uint16_t TFS = 36;
const uint16_t RFS = 35;
const uint16_t DATAIN = 34;
const uint16_t DATAOUT = 33;
const uint16_t CS_pin = 0;

const uint8_t PIN_A = 22;
const uint8_t PIN_B = 21;
const uint8_t PIN_C = 20;
const uint8_t PIN_PRESSURE = A15;

// Constants
const double SCLK_DELAY = 0.25;
const double RW_DELAY = 0.5;
const double CONVST_DELAY = 6;
const uint16_t command = 0b1111111111111111; // Read command (0xFFF)

// Function prototypes
void setupADC();
int16_t readADChannel(byte ch_number);
float readRegister();
void select_pressure_sensor(uint8_t num);
uint16_t get_pressure(uint8_t num);

#endif // UTILITIES_H