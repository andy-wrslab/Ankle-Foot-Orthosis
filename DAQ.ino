#define CUSTOM
#include "teensySensoryMB.h"
#include "EasyCAT.h"
#include <SPI.h>
#include "PINOUT.h"
#include "SensorData.h"

// Filter - properties: Butterworth, 2nd order, 12 HZ passband--Implemented by Lorenzo  
const double a[] = {1.0, -1.911197067426073, 0.914975834801433};
const double b[] = {0.0009446918438401619, 0.001889383687680, 0.0009446918438401619};

// CLOCK AT 600 MHZ
const double         CONVST_DELAY =    6;
const double           SCLK_DELAY = 0.25;
const double             RW_DELAY = 0.50;

const int     READ_TIMER_INTERVAL =  200; // [5kHz]
const int   FILTER_TIMER_INTERVAL = 1000; // [1kHz]

const int             NUM_SENSORS = 4;
const int             PNTS_TO_AVG = 5;
unsigned int           ADC_cycles = 0; 
unsigned long             t_blink = 0;
bool                   led_status = 0;

volatile int          raw_encoder = 0;
volatile float           pot_prev = 0;
volatile float           pot_curr = 0;

EasyCAT                   EASYCAT(10);
SensorData       sensors[NUM_SENSORS];   // {potentiometer, encoder, pressure, velocity}
IntervalTimer        readSensorsTimer; 
IntervalTimer      filterSensorsTimer;

void  setup() {
  Serial.begin(9600);
  setupLED();
  setupEASYCAT();
  setupSensors();
  setupTimers();
}

void  loop() {
  EASYCAT.MainTask();
  if (millis() - t_blink >= 1000) {
      t_blink = millis();
      digitalWrite(PIN_LED, led_status = !led_status);
      
  }
}



void  setupLED() {
  pinMode(PIN_LED, OUTPUT);
}

void  setupEASYCAT() {
  Serial.println ("EasyCAT - Generic EtherCAT slave");
  if (EASYCAT.Init() == true)
  {
    Serial.print ("initialized");                                 
  }                                                               //
  else                                                            // initialization failed   
  {                                                               // the EasyCAT board was not recognized
    Serial.print ("initialization failed");                       //                                                 
  }
}

void  setupSensors() {
  // ADC
  pinMode(PIN_CONVST, OUTPUT);
  pinMode(PIN_SCLK, OUTPUT);
  pinMode(PIN_TFS, OUTPUT);
  pinMode(PIN_RFS, OUTPUT);
  pinMode(PIN_DATAOUT, OUTPUT);
  pinMode(PIN_DATAIN, INPUT);
  digitalWrite(PIN_CONVST, LOW);
  digitalWrite(PIN_SCLK, HIGH);
  digitalWrite(PIN_TFS, HIGH);
  digitalWrite(PIN_RFS, HIGH);
  digitalWrite(PIN_DATAOUT, LOW);

  // Encoder
  SPI1.begin();
  pinMode(PIN_CS, OUTPUT);

  // Pressure
  pinMode(PIN_A, OUTPUT);
  pinMode(PIN_B, OUTPUT);
  pinMode(PIN_C, OUTPUT);
}

void  setupTimers() {
  readSensorsTimer.begin(readSensors, READ_TIMER_INTERVAL);
  filterSensorsTimer.begin(filterSensors, FILTER_TIMER_INTERVAL);
}

int   readADChannel(byte ch_number) {
  byte ctrl;
  uint8_t ch;
  uint16_t indata;
  int16_t  rawdata;

  digitalWrite(PIN_TFS, LOW); //pull down /TFS to write the data
  
  ch_number -= 1;
  ctrl = 0x00; //set control register
  
  for (int i = 0; i < 3; i++)
  {
    bitWrite(ctrl, i + 2, bitRead(ch_number, i));
  }

  for (int i = 0; i < 5; i++)
  {
    digitalWrite(PIN_SCLK, HIGH);
    digitalWrite(PIN_DATAOUT, bitRead(ctrl, 4 - i));
    delayMicroseconds(SCLK_DELAY);
    digitalWrite(PIN_SCLK, LOW); // on the falling edge the data bit is actually written to ADC
    delayMicroseconds(SCLK_DELAY);
  }
  // provide the 6th falling edge as per specsheet
  digitalWrite(PIN_SCLK, HIGH);
  delayMicroseconds(SCLK_DELAY);
  digitalWrite(PIN_SCLK, LOW);
  delayMicroseconds(SCLK_DELAY);
  digitalWrite(PIN_TFS, HIGH);// restore TFS signal

  // start conversion
  delayMicroseconds(RW_DELAY);
  digitalWrite(PIN_CONVST, HIGH);  // initiate conversion
  delayMicroseconds(CONVST_DELAY); // conversion ends 5.9 us later
  digitalWrite(PIN_CONVST, LOW);  // restore start conversion signal

  // pull down /RFS to read the data
  digitalWrite(PIN_RFS, LOW); // since SCLK is low now, the next rising edge will clock the data
  delayMicroseconds(SCLK_DELAY);
  indata = 0x0000;
  for (int i = 0; i < 16; i++)
  {
    digitalWrite(PIN_SCLK, HIGH); // data bit is clocked 35ns after this rising edge
    delayMicroseconds(SCLK_DELAY);
    digitalWrite(PIN_SCLK, LOW);
    bitWrite(indata, 15 - i, digitalRead(PIN_DATAIN)); // read the data right after the falling edge
    delayMicroseconds(SCLK_DELAY);
  }
  digitalWrite(PIN_RFS, HIGH); // restore the RFS signal and put ADC in tristate [20ns min after last falling edge]

  delayMicroseconds(RW_DELAY); // wait before the next r/w operation

  // DEBUG
  //obtain 4-bit channel information
  ch = (uint8_t) ((indata >> 12) & 0x000F);

  if (ch == (uint8_t) (ch_number))
  {
    //obtain 12-bit raw data (without channel information)
    int addme = -bitRead(indata, 11) * 2048;
    rawdata = (int16_t) (indata & 0x07FF);
    rawdata += addme;
    /////////////////
    // rawdata = 0;
    ////////////////
  }
  else
  {
    // rawdata = -1023; ////// remove this ELSE
    rawdata = (int16_t) (ch);
  }
  return rawdata;
}

int   readEncoder() {
  SPI1.beginTransaction(SPISettings(3000000, MSBFIRST, SPI_MODE1));

  //--sending the command
  digitalWrite(PIN_CS, LOW);
  SPI1.transfer16(0xFFFF);
  digitalWrite(PIN_CS, HIGH);

  //--receiving the reading
  digitalWrite(PIN_CS, LOW);
  raw_encoder = SPI1.transfer16(0xFFFF);
  digitalWrite(PIN_CS, HIGH);

  SPI1.endTransaction();

  raw_encoder = raw_encoder & 0b0011111111111111; //removing the top 2 bits (PAR and EF)
  return raw_encoder;
}

int   readPressure(uint8_t num) {
    // Simplified using bit shifting
    digitalWrite(PIN_A, (num & (1 << 1)) ? HIGH : LOW); // Set PIN_A based on bit 1
    digitalWrite(PIN_B, (num & (1 << 0)) ? HIGH : LOW); // Set PIN_B based on bit 0
    digitalWrite(PIN_C, (num & (1 << 2)) ? HIGH : LOW); // Set PIN_C based on bit 2

    delayMicroseconds(4);
    return analogRead(PIN_PRESSURE);
}

float readVelocity() {
  pot_prev = pot_curr;
  pot_curr = readADChannel(CH_NUM_LC);
  return (pot_curr - pot_prev) / 0.2 / 1000;
}

void  readSensors() {
  sensors[0].sum += readADChannel(CH_NUM_LC);      // read potentiometer
  sensors[1].sum += readEncoder();                    // read encoder
  sensors[2].sum += readPressure(3) + readPressure(4); // read pressure
  sensors[3].sum += readVelocity();                   // read velocity

  ADC_cycles++;
  if (ADC_cycles == PNTS_TO_AVG) {
    ADC_cycles = 0;
    for (int i = 0; i < NUM_SENSORS; i++) {
        sensors[i].value = sensors[i].sum / PNTS_TO_AVG;
        sensors[i].sum = 0;
    }
  }
}

void  filterSensors() {
    for (int i = 0; i < NUM_SENSORS; i++) {
        sensors[i].filtered_value = b[0] * sensors[i].value;
        for (int k = 1; k < 3; k++) {
            sensors[i].filtered_value +=   b[k] * sensors[i].buff_raw [k - 1]
                                         - a[k] * sensors[i].buff_filt[k - 1];
        }
        for (int k = 3; k > 0; k--) {
            sensors[i].buff_filt[k] = sensors[i].buff_filt[k - 1];
        }
        sensors[i].buff_raw[0]  = sensors[i].value;
        sensors[i].buff_filt[0] = sensors[i].filtered_value;
    }
    noInterrupts();
    application();
    interrupts();
}

void  application() {
    EASYCAT.BufferIn.Cust.Force1 = sensors[0].filtered_value;
    EASYCAT.BufferIn.Cust.Force2 = sensors[1].filtered_value;
    EASYCAT.BufferIn.Cust.Force3 = sensors[2].filtered_value;
    EASYCAT.BufferIn.Cust.Force4 = sensors[3].filtered_value;
}