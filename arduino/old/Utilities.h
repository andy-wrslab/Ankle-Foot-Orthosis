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

// Constants
const double SCLK_DELAY = 0.25;
const double RW_DELAY = 0.5;
const double CONVST_DELAY = 6;

void setupADC() {
    pinMode(CONVST, OUTPUT);
    pinMode(SCLK, OUTPUT);
    pinMode(TFS, OUTPUT);
    pinMode(RFS, OUTPUT);
    pinMode(DATAOUT, OUTPUT);
    pinMode(DATAIN, INPUT);

    digitalWrite(CONVST, LOW);
    digitalWrite(SCLK, HIGH);
    digitalWrite(RFS, HIGH);
    digitalWrite(TFS, HIGH);
    digitalWrite(DATAOUT, LOW);
}

int16_t readADChannel(byte ch_number) {
    byte ctrl;
    uint8_t ch;
    uint16_t indata;
    int16_t rawdata;

    digitalWrite(TFS, LOW);

    ch_number -= 1;
    ctrl = 0x00;

    for (int i = 0; i < 3; i++) {
        bitWrite(ctrl, i + 2, bitRead(ch_number, i));
    }

    for (int i = 0; i < 5; i++) {
        digitalWrite(SCLK, HIGH);
        digitalWrite(DATAOUT, bitRead(ctrl, 4 - i));
        delayMicroseconds(SCLK_DELAY);
        digitalWrite(SCLK, LOW);
        delayMicroseconds(SCLK_DELAY);
    }

    digitalWrite(SCLK, HIGH);
    delayMicroseconds(SCLK_DELAY);
    digitalWrite(SCLK, LOW);
    delayMicroseconds(SCLK_DELAY);
    digitalWrite(TFS, HIGH);

    delayMicroseconds(RW_DELAY);
    digitalWrite(CONVST, HIGH);
    delayMicroseconds(CONVST_DELAY);
    digitalWrite(CONVST, LOW);

    digitalWrite(RFS, LOW);
    delayMicroseconds(SCLK_DELAY);
    indata = 0x0000;
    for (int i = 0; i < 16; i++) {
        digitalWrite(SCLK, HIGH);
        delayMicroseconds(SCLK_DELAY);
        digitalWrite(SCLK, LOW);
        bitWrite(indata, 15 - i, digitalRead(DATAIN));
        delayMicroseconds(SCLK_DELAY);
    }
    digitalWrite(RFS, HIGH);

    delayMicroseconds(RW_DELAY);

    ch = (uint8_t)((indata >> 12) & 0x000F);

    if (ch == (uint8_t)(ch_number)) {
        int addme = -bitRead(indata, 11) * 2048;
        rawdata = (int16_t)(indata & 0x07FF);
        rawdata += addme;
    } else {
        rawdata = (int16_t)(ch);
    }
    return rawdata;
}

float readRegister() {
    SPI1.beginTransaction(SPISettings(3000000, MSBFIRST, SPI_MODE1));

    digitalWrite(CS_pin, LOW);
    SPI1.transfer16(command);
    digitalWrite(CS_pin, HIGH);

    digitalWrite(CS_pin, LOW);
    raw_encoder = SPI1.transfer16(command);
    digitalWrite(CS_pin, HIGH);

    SPI1.endTransaction();

    raw_encoder = raw_encoder & 0b0011111111111111;
    degAngle = (float)raw_encoder;
    return degAngle;
}

void select_pressure_sensor(uint8_t num) {
    digitalWrite(PIN_A, (num >> 2) & 0x01);
    digitalWrite(PIN_B, (num >> 1) & 0x01);
    digitalWrite(PIN_C, num & 0x01);
}

uint16_t get_pressure(uint8_t num) {
    uint16_t val = 0;
    select_pressure_sensor(num);

    delayMicroseconds(4);
    val = analogRead(PIN_PRESSURE);

    if (val > 1023) {
        val = 1500;
    }
    return ((uint16_t)val);
}

#endif // UTILITIES_H