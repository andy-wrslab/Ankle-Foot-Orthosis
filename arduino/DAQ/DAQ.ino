#define CUSTOM
#include "teensySensoryMB_32_Inputs.h"
#include "EasyCAT.h"
#include <SPI.h>
#include "PINOUT.h"
#include "SensorData.h"
#include "IMU.h"
#include <TeensyThreads.h>

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
volatile float    encoder_reading = 0;
volatile float        pot_reading = 0;
volatile float      heel_pressure = 0;



EasyCAT                   EASYCAT(10);
SensorData       sensors[NUM_SENSORS];   // {potentiometer, encoder, pressure, velocity}
IntervalTimer        readSensorsTimer; 
IntervalTimer      filterSensorsTimer;

uint8_t nPacketStreamingData = sizeof(structStreamingData);
boolean reset_imu;
boolean sig;
unsigned long nowTime = 0;
unsigned long startTime;
float yaw1, pitch1, roll1;

uint16_t p[] = {0, 0, 0, 0, 0, 0, 0, 0};
uint16_t p_sum[] = {1000, 1000}; // sum all the pressure
uint16_t p_heel = 0;
uint16_t p_toe = 0;
uint16_t p_mball = 0;


void readIMUTask() {
  while (true) {
    readIMU();
    threads.yield();
  }
}

void  setup() {
  Serial.begin(9600);
  setupLED();
  setupEASYCAT();
  setupSensors();
  setupIMU();
  setupTimers();
  threads.addThread(readIMUTask);
  
}

int t = micros();

void  loop() {
  if (micros() - t > 500) {
    application();
    EASYCAT.MainTask();
    Serial.println(uStreamingDataIMU1.sData.lAcc.az);

    t = millis();
  }

  Serial.println("?oasdaoi");

  noInterrupts();
  pot_reading = readADChannel(CH_NUM_LC);
  encoder_reading = readEncoder();
  heel_pressure = readPressure(0) + readPressure(2);
  interrupts();
  readAllPressure();
  nowTime = micros() - startTime;
  updateEstimator();
  
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

float readEncoder() {
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

  return raw_encoder / 16384.0 * 360.0;
}

int   readPressure(uint8_t num) {
    // Simplified using bit shifting
    digitalWrite(PIN_A, (num & (1 << 1)) ? HIGH : LOW); // Set PIN_A based on bit 1
    digitalWrite(PIN_B, (num & (1 << 0)) ? HIGH : LOW); // Set PIN_B based on bit 0
    digitalWrite(PIN_C, (num & (1 << 2)) ? HIGH : LOW); // Set PIN_C based on bit 2

    delayMicroseconds(4);
    return analogRead(PIN_PRESSURE);
}


void functionAFO(float * phi, float & theta, float & omega, float * a, float dt, float yaw) {
  float val = 0.0f; // compute the sum of a*sin(phi)
  for (uint8_t h = 0; h < AFO_m; h++) {
    val = val + a[h] * sin(phi[h]);
  }
  float F;
  F = yaw - theta - val; // error signal
  // update state
  for (uint8_t h = 0; h < AFO_m; h++) {
    phi[h] = fmod(phi[h] + dt * ((h + 1) * omega + AFO_eps * F * cos(phi[h])), 2 * pi);
  }
  // update omega
  omega = omega + dt * AFO_eps * F * cos(phi[0]);
  // update a
  for (uint8_t h = 0; h < AFO_m; h++) {
    a[h] = a[h] + dt * AFO_v * F * sin(phi[h]);
  }
  // update theta
  theta = theta + dt * AFO_v * F;
}

void VelocityEstimatorUpdate_v2(structVelocityEstimator & VelocityEstimator, const uint8_t * Gait_State, float ax, float ay, float az, float t) {
  // Updating
  VelocityEstimator.ax[VelocityEstimator.iter] = ax * g_NJ;
  VelocityEstimator.ay[VelocityEstimator.iter] = ay * g_NJ;
  VelocityEstimator.az[VelocityEstimator.iter] = az * g_NJ;
  VelocityEstimator.aM[VelocityEstimator.iter] = sqrt(pow(VelocityEstimator.ax[VelocityEstimator.iter], 2) + pow(VelocityEstimator.ay[VelocityEstimator.iter], 2) + pow(VelocityEstimator.az[VelocityEstimator.iter], 2));
  VelocityEstimator.t[VelocityEstimator.iter] = t;

  // Gait Event Detection
  if (Gait_State[0] == 1) // First Contact Detected
  {
    if (VelocityEstimator.FC_iter == 0)
    {
      VelocityEstimator.FC_idx[0] = VelocityEstimator.iter;
      VelocityEstimator.FC_iter = 1;
    }

    if (VelocityEstimator.FC_iter == 1 && (t - VelocityEstimator.t[VelocityEstimator.FC_idx[0]] > 0.5))
    {
      VelocityEstimator.FC_idx[1] = VelocityEstimator.iter;
      VelocityEstimator.FC_iter = 2;
    }

    if (VelocityEstimator.FC_iter == 2 && (t - VelocityEstimator.t[VelocityEstimator.FC_idx[1]] > 0.5)) // Missing Last Contact, re-initial
    {
      VelocityEstimator.FC_idx[0] = VelocityEstimator.iter;
      VelocityEstimator.FC_iter = 1;
      VelocityEstimator.LC_iter = 0;
      VelocityEstimator.FF_iter1 = 0;
      VelocityEstimator.FF_iter2 = 0;
    }
  }

  if (Gait_State[1] == 1 && VelocityEstimator.FC_iter >= 1) // Last Contact Detected
  {
    if (VelocityEstimator.LC_iter == 0)
    {
      VelocityEstimator.LC_idx[0] = VelocityEstimator.iter;
      VelocityEstimator.LC_iter = 1;
    }

    if (VelocityEstimator.LC_iter == 1 && (t - VelocityEstimator.t[VelocityEstimator.LC_idx[0]] > 0.5))
    {
      VelocityEstimator.LC_idx[1] = VelocityEstimator.iter;
      VelocityEstimator.LC_iter = 2;
    }

    if (VelocityEstimator.LC_iter == 2 && (t - VelocityEstimator.t[VelocityEstimator.LC_idx[1]] > 0.5)) // Missing First Contact, re-initial
    {
      VelocityEstimator.FC_iter = 0;
      VelocityEstimator.LC_iter = 0;
      VelocityEstimator.FF_iter1 = 0;
      VelocityEstimator.FF_iter2 = 0;
    }
  }

  if ((VelocityEstimator.Gait_State[0] + VelocityEstimator.Gait_State[1] < 2) && (Gait_State[2] + Gait_State[3] == 2) && VelocityEstimator.FC_iter >= 1) // Foot-flat start (CHANGING TO TOE OFF)
  {
    if (VelocityEstimator.FF_iter1 == 0)
    {
      VelocityEstimator.FF_idx1[0] = VelocityEstimator.iter;
      VelocityEstimator.FF_iter1 = 1;
    }

    if (VelocityEstimator.FF_iter1 == 1 && VelocityEstimator.FC_iter == 1)
    {

    }

    if (VelocityEstimator.FF_iter1 == 1 && VelocityEstimator.FC_iter == 2)
    {
      VelocityEstimator.FF_idx1[1] = VelocityEstimator.iter;
      VelocityEstimator.FF_iter1 = 2;
    }

    if (VelocityEstimator.FF_iter1 == 2 && VelocityEstimator.FC_iter == 2)
    {

    }

  }

  if ((VelocityEstimator.Gait_State[0] + VelocityEstimator.Gait_State[1] == 2) && (Gait_State[2] + Gait_State[3] < 2) && VelocityEstimator.FC_iter >= 1) // Foot-flat end
  {
    if (VelocityEstimator.FF_iter2 == 0)
    {
      VelocityEstimator.FF_idx2[0] = VelocityEstimator.iter;
      VelocityEstimator.FF_iter2 = 1;
    }

    if (VelocityEstimator.FF_iter2 == 1 && VelocityEstimator.FC_iter == 1)
    {
      VelocityEstimator.FF_idx2[0] = VelocityEstimator.iter;
    }

    if (VelocityEstimator.FF_iter2 == 1 && VelocityEstimator.FC_iter == 2)
    {
      VelocityEstimator.FF_idx2[1] = VelocityEstimator.iter;
      VelocityEstimator.FF_iter2 = 2;
    }

    if (VelocityEstimator.FF_iter2 == 2 && VelocityEstimator.FC_iter == 2)
    {
      VelocityEstimator.FF_idx2[1] = VelocityEstimator.iter;
    }
  }

  // Velocity Estimation trigger
  if (VelocityEstimator.FC_iter == 2 && VelocityEstimator.LC_iter == 2)
  {
    uint16_t start_idx;
    uint16_t end_idx;
    float    minAcc;
    uint8_t cond =
      ((VelocityEstimator.t[VelocityEstimator.FC_idx[0]] <= VelocityEstimator.t[VelocityEstimator.FF_idx1[0]]) << 0) |
      ((VelocityEstimator.t[VelocityEstimator.FF_idx1[0]] <= VelocityEstimator.t[VelocityEstimator.LC_idx[0]]) << 1) |
      ((VelocityEstimator.t[VelocityEstimator.FC_idx[0]] <= VelocityEstimator.t[VelocityEstimator.FF_idx2[0]]) << 2) |
      ((VelocityEstimator.t[VelocityEstimator.FF_idx2[0]] <= VelocityEstimator.t[VelocityEstimator.LC_idx[0]]) << 3) |
      ((VelocityEstimator.t[VelocityEstimator.FC_idx[1]] <= VelocityEstimator.t[VelocityEstimator.FF_idx1[1]]) << 4) |
      ((VelocityEstimator.t[VelocityEstimator.FF_idx1[1]] <= VelocityEstimator.t[VelocityEstimator.LC_idx[1]]) << 5) |
      ((VelocityEstimator.t[VelocityEstimator.FC_idx[1]] <= VelocityEstimator.t[VelocityEstimator.FF_idx2[1]]) << 6) |
      ((VelocityEstimator.t[VelocityEstimator.FF_idx2[1]] <= VelocityEstimator.t[VelocityEstimator.LC_idx[1]]) << 7) ;

    if (cond == 0xff)
    {
      // Case 1: Select the minimum magnitude of acceleration in FF phase
      start_idx = VelocityEstimator.FF_idx1[0];
      minAcc   = VelocityEstimator.aM[start_idx];
      for (uint16_t h = (VelocityEstimator.FF_idx1[0] + 1) % 1000; h != VelocityEstimator.FF_idx2[0]; h = (1 + h) % 1000)
      {
        if ( VelocityEstimator.aM[h] < minAcc)
        {
          start_idx = h;
          minAcc = VelocityEstimator.aM[h];
        }
      }

      end_idx = VelocityEstimator.FF_idx1[1];
      minAcc = VelocityEstimator.aM[end_idx];
      for (uint16_t h = (VelocityEstimator.FF_idx1[1] + 1) % 1000; h != VelocityEstimator.FF_idx2[1]; h = (1 + h) % 1000)
      {
        if ( VelocityEstimator.aM[h] < minAcc)
        {
          end_idx = h;
          minAcc = VelocityEstimator.aM[h];
        }
      }
    }
    else
    {
      // Case 3: Select the minimum magnitude of acceleration
      start_idx = VelocityEstimator.FC_idx[0];
      minAcc   = VelocityEstimator.aM[start_idx];
      for (uint16_t h = (VelocityEstimator.FC_idx[0] + 1) % 1000; h != VelocityEstimator.LC_idx[0]; h = (1 + h) % 1000)
      {
        if ( VelocityEstimator.aM[h] < minAcc)
        {
          start_idx = h;
          minAcc = VelocityEstimator.aM[h];
        }
      }

      end_idx = VelocityEstimator.FC_idx[1];
      minAcc = VelocityEstimator.aM[end_idx];
      for (uint16_t h = (VelocityEstimator.FC_idx[1] + 1) % 1000; h != VelocityEstimator.LC_idx[1]; h = (1 + h) % 1000)
      {
        if ( VelocityEstimator.aM[h] < minAcc)
        {
          end_idx = h;
          minAcc = VelocityEstimator.aM[h];
        }
      }
    }


    VelocityEstimator.vx[start_idx] = 0;
    VelocityEstimator.vy[start_idx] = 0;
    VelocityEstimator.vz[start_idx] = 0;
    VelocityEstimator.px[start_idx] = 0;
    VelocityEstimator.py[start_idx] = 0;
    VelocityEstimator.pz[start_idx] = 0;
    // ZUPT (foot-flat phase to foot-flat phase) + VDC (Assuming linear drift)
    for (uint16_t h = start_idx; h != end_idx; h = (1 + h) % 1000)
    {
      VelocityEstimator.vx[(1 + h) % 1000] = VelocityEstimator.vx[h] + 0.5 * (VelocityEstimator.ax[h] + VelocityEstimator.ax[(1 + h) % 1000]) * (VelocityEstimator.t[(1 + h) % 1000] - VelocityEstimator.t[h]);
      VelocityEstimator.vy[(1 + h) % 1000] = VelocityEstimator.vy[h] + 0.5 * (VelocityEstimator.ay[h] + VelocityEstimator.ay[(1 + h) % 1000]) * (VelocityEstimator.t[(1 + h) % 1000] - VelocityEstimator.t[h]);
      VelocityEstimator.vz[(1 + h) % 1000] = VelocityEstimator.vz[h] + 0.5 * (VelocityEstimator.az[h] + VelocityEstimator.az[(1 + h) % 1000]) * (VelocityEstimator.t[(1 + h) % 1000] - VelocityEstimator.t[h]);
    }

    float vx_drift = VelocityEstimator.vx[end_idx] / (VelocityEstimator.t[end_idx] - VelocityEstimator.t[start_idx]);
    float vy_drift = VelocityEstimator.vy[end_idx] / (VelocityEstimator.t[end_idx] - VelocityEstimator.t[start_idx]);
    float vz_drift = VelocityEstimator.vz[end_idx] / (VelocityEstimator.t[end_idx] - VelocityEstimator.t[start_idx]);

    for (uint16_t h = start_idx; h != end_idx; h = (1 + h) % 1000)
    {
      VelocityEstimator.vx[(1 + h) % 1000] = VelocityEstimator.vx[(1 + h) % 1000] - vx_drift * (VelocityEstimator.t[(1 + h) % 1000] - VelocityEstimator.t[start_idx]);
      VelocityEstimator.px[(1 + h) % 1000] = VelocityEstimator.px[h] + 0.5 * (VelocityEstimator.vx[h] + VelocityEstimator.vx[(1 + h) % 1000]) * (VelocityEstimator.t[(1 + h) % 1000] - VelocityEstimator.t[h]);

      VelocityEstimator.vy[(1 + h) % 1000] = VelocityEstimator.vy[(1 + h) % 1000] - vy_drift * (VelocityEstimator.t[(1 + h) % 1000] - VelocityEstimator.t[start_idx]);
      VelocityEstimator.py[(1 + h) % 1000] = VelocityEstimator.py[h] + 0.5 * (VelocityEstimator.vy[h] + VelocityEstimator.vy[(1 + h) % 1000]) * (VelocityEstimator.t[(1 + h) % 1000] - VelocityEstimator.t[h]);

      VelocityEstimator.vz[(1 + h) % 1000] = VelocityEstimator.vz[(1 + h) % 1000] - vz_drift * (VelocityEstimator.t[(1 + h) % 1000] - VelocityEstimator.t[start_idx]);
      VelocityEstimator.pz[(1 + h) % 1000] = VelocityEstimator.pz[h] + 0.5 * (VelocityEstimator.vz[h] + VelocityEstimator.vz[(1 + h) % 1000]) * (VelocityEstimator.t[(1 + h) % 1000] - VelocityEstimator.t[h]);
    }

    //VelocityEstimator.SL=sqrt(pow(VelocityEstimator.px[end_idx],2)+pow(VelocityEstimator.py[end_idx],2)+pow(VelocityEstimator.pz[end_idx],2));
    //VelocityEstimator.SV=VelocityEstimator.SL/(VelocityEstimator.t[VelocityEstimator.LC_idx[1]]-VelocityEstimator.t[VelocityEstimator.LC_idx[0]]);
    float SL = sqrt(pow(VelocityEstimator.px[end_idx], 2) + pow(VelocityEstimator.py[end_idx], 2) + pow(VelocityEstimator.pz[end_idx], 2));
    VelocityEstimator.SV = SL / (VelocityEstimator.t[VelocityEstimator.LC_idx[1]] - VelocityEstimator.t[VelocityEstimator.LC_idx[0]]);

    VelocityEstimator.SL = SL;

    VelocityEstimator.FC_idx[0] = VelocityEstimator.FC_idx[1];
    VelocityEstimator.FC_iter = 1;

    VelocityEstimator.LC_idx[0] = VelocityEstimator.LC_idx[1];
    VelocityEstimator.LC_iter = 1;

    VelocityEstimator.FF_idx1[0] = VelocityEstimator.FF_idx1[1];
    VelocityEstimator.FF_iter1 = 1;

    VelocityEstimator.FF_idx2[0] = VelocityEstimator.FF_idx2[1];
    VelocityEstimator.FF_iter2 = 1;
    // }
    // else
    // {VelocityEstimator.SL= cond/100.0;}
  }

  VelocityEstimator.Gait_State[0] = Gait_State[2];
  VelocityEstimator.Gait_State[1] = Gait_State[3];
  VelocityEstimator.iter = (VelocityEstimator.iter + 1) % 1000;
}

float fmodC(float a, float b) {
  float c = fmod(a, b);
  if (c < 0)
  {
    c = c + b;
  }
  return c;
}

void GaitEventDetector_v2(uint16_t * pSum, uint16_t pHeel, uint16_t pToe, uint8_t * GaitState, float omega, float * tFC, float * tLC, float tStar, float AFO, float & AFOc, float & phase_error, float * phase_error_hat, float & 6 whatever_error, float * AFO_phi_error_dot, float dt, float & AFOc_simple, float AFO_phi_error_Kp) {
  AFO = fmodC(AFO, 2 * pi);
  // AFO_corrected updates based on First Contact
  if (pSum[0] <= threshold_pressure_sum && pSum[1] > threshold_pressure_sum)
  {
    GaitState[0] = 1;
    if (tStar - tFC[1] > rho * 2 * pi / omega)
    {
      tFC[0] = tFC[1];
      tFC[1] = tStar;

      if (AFO >= 0 && AFO < pi) // AFO from 0 to pi
      {
        phase_error = -AFO;
      }
      else
      {
        phase_error = 2 * pi - AFO;
      }

      if (phase_error > 0.5 * pi && phase_error_hat[1] < -0.5 * pi)
      {
        phase_error_hat[0] = phase_error_hat[1];
        phase_error_hat[1] = phase_error - 2 * pi;
      }
      else if (phase_error < -0.5 * pi && phase_error_hat[1] > 0.5 * pi)
      {
        phase_error_hat[0] = phase_error_hat[1];
        phase_error_hat[1] = phase_error + 2 * pi;
      }
      else
      {
        phase_error_hat[0] = phase_error_hat[1];
        phase_error_hat[1] = phase_error;
      }

    }
    else
    {

    }
  }
  else
  {
    GaitState[0] = 0;
  }

  AFOc_simple = fmodC(AFO + phase_error_hat[1], 2 * pi); // correct AFO simple method
  AFO_phi_error_dot[0] = AFO_phi_error_dot[1];
  float eps = AFO_phi_error_Kp * (phase_error_hat[1] - AFO_phi_error);
  AFO_phi_error_dot[1] = eps * omega * exp(-omega * (tStar - tFC[1]));
  AFO_phi_error       = AFO_phi_error + 0.5 * dt * (AFO_phi_error_dot[0] + AFO_phi_error_dot[1]);
  AFOc = fmodC(AFO + AFO_phi_error, 2 * pi);

  // Last Contact
  if (pSum[0] > threshold_pressure_sum && pSum[1] <= threshold_pressure_sum)
  {
    GaitState[1] = 1;
    if (tStar - tLC[1] > rho * 2 * pi / omega)
    {
      tLC[0] = tLC[1];
      tLC[1] = tStar;

    }
    else
    {

    }
  }
  else
  {
    GaitState[1] = 0;
  }

  // Updating gait state
  if (pHeel >= threshold_pressure_state)
  {
    GaitState[2] = 1;
  }
  else
  {
    GaitState[2] = 0;
  }

  if (pToe >= threshold_pressure_state)
  {
    GaitState[3] = 1;
  }
  else
  {
    GaitState[3] = 0;
  }

}

void setupIMU() {
  IMU1.begin(115200);
  delay(1000);
  IMU1.flush();
  YEIsettingsHeader(IMU1);
  YEIwriteCommand(IMU1, CMD_STOP_STREAMING);
  IMU1.flush();
  delay(3000);
  YEIwriteCommand(IMU1, CMD_SET_ACCELEROMETER_RANGE, ACCELEROMETER_RANGE_24G);
  YEIwriteCommand(IMU1, CMD_SET_GYROSCOPE_RANGE, GYROSCOPE_RANGE_2000);
  YEIwriteCommand(IMU1, CMD_SET_COMPASS_RANGE, COMPASS_RANGE_1_3);
  YEIwriteCommand(IMU1, CMD_SET_CALIBRATION_MODE, CALIBRATION_MODE_BIAS_SCALE);
  YEIwriteCommand(IMU1, CMD_SET_REFERENCE_VECTOR_MODE, REFERENCE_VECTOR_MULTI_REFERENCE_MODE);
  YEIwriteCommand(IMU1, CMD_SET_COMPASS_ENABLE, FALSE);
  YEIwriteCommandNoDelay(IMU1, CMD_BEGIN_GYROSCOPE_AUTOCALIBRATION);
  delay(3000);
  YEIwriteCommandNoDelay(IMU1, CMD_RESET_FILTER);
  delay(1000);
  YEIsetStreamingMode(IMU1, READ_TARED_ORIENTATION_AS_QUATERNION, READ_CORRECTED_ACCELEROMETER_VECTOR, NO_SLOT, NO_SLOT, NO_SLOT, NO_SLOT, NO_SLOT, NO_SLOT);

  sStreamingTime.interval = 2000; //10000; //[us]
  sStreamingTime.duration = 0xFFFFFFFF;
  sStreamingTime.delay = 0;  //[us]
  YEIsetStreamingTime(IMU1);
  IMU1.flush();
  reset_imu = FALSE;
  sig = FALSE;
  startTime = micros();
}

void readIMU() {
  if (!reset_imu)
  {
    reset_imu = true;

    YEIwriteCommandNoDelay(IMU1, CMD_STOP_STREAMING);
    IMU1.flush();

    YEIsetStreamingMode(IMU1, READ_TARED_ORIENTATION_AS_QUATERNION, 
                              READ_CORRECTED_LINEAR_ACCELERATION, 
                              NO_SLOT, 
                              NO_SLOT, 
                              NO_SLOT, 
                              NO_SLOT, 
                              NO_SLOT, 
                              NO_SLOT);
    YEIwriteCommandNoDelay(IMU1, CMD_TARE_WITH_CURRENT_ORIENTATION);
    IMU1.flush();
    YEIsetStreamingTime(IMU1);
    sig = !sig;
  }
  else
  {
    // Read IMU data every time
    YEIgetStreamingBatch(uStreamingDataIMU1);
    quaternion2euler(uStreamingDataIMU1.sData.q.qw, uStreamingDataIMU1.sData.q.qy, uStreamingDataIMU1.sData.q.qz, uStreamingDataIMU1.sData.q.qx, yaw1, pitch1, roll1);
  }
}

void updateEstimator() {
  // AFO
  AFO_t[0]=AFO_t[1];
  AFO_t[1]=nowTime;
  if (AFO_t[1]-AFO_t[0]>0)
  {
    AFO_dt= (AFO_t[1]-AFO_t[0])/1e6;
  }
  else
  { 
    AFO_t[1]= AFO_t[0]+3100;
  }

  functionAFO(AFO_phi,AFO_theta,AFO_omega,AFO_a,AFO_dt,pitch1);
  GaitEventDetector_v2(p_sum, p_heel, p_toe, Gait_State, AFO_omega, t_FC, t_LC, AFO_t[1] / 1e6, AFO_phi[0], AFO_corrected, Phase_Error, Phase_Error_Hat, AFO_phi_error, AFO_phi_error_dot, AFO_dt, AFOc_simple, AFO_phi_error_Kp);
  VelocityEstimatorUpdate_v2(VelocityEstimator, Gait_State, -uStreamingDataIMU1.sData.lAcc.ax, -uStreamingDataIMU1.sData.lAcc.az, uStreamingDataIMU1.sData.lAcc.ay, AFO_t[1] / 1e6);

}

void readAllPressure() {
    p_sum[0] = p_sum[1];
    p_sum[1] = 0;
    // // Read Pressure
    for (uint8_t h = 0; h < 8; h++) {
      p[h] = readPressure(h+1);
      p_sum[1] = p_sum[1] + p[h];
    }

    p_heel = p[1] + p[7];
    p_toe  = p[2] + p[5];
    p_mball = p_toe + p[0] + p[3] + p[4]+ p[6];
}

void  readSensors() {
  sensors[0].sum += pot_reading;      // read potentiometer
  sensors[1].sum += encoder_reading;                    // read encoder
  sensors[2].sum += heel_pressure; // read pressure

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
}

void  application() {
  EASYCAT.BufferIn.Cust.Force1 = sensors[0].value;
  EASYCAT.BufferIn.Cust.Force2 = sensors[1].value;
  EASYCAT.BufferIn.Cust.Force3 = sensors[2].value;
  EASYCAT.BufferIn.Cust.Force4 = sensors[0].filtered_value;
  EASYCAT.BufferIn.Cust.Force5 = sensors[1].filtered_value;
  EASYCAT.BufferIn.Cust.Force6 = sensors[2].filtered_value;
  EASYCAT.BufferIn.Cust.Force7 = VelocityEstimator.SV;
  EASYCAT.BufferIn.Cust.Force8 = VelocityEstimator.SL;
  EASYCAT.BufferIn.Cust.Force9 = yaw1;
  EASYCAT.BufferIn.Cust.Force10 = pitch1;
  EASYCAT.BufferIn.Cust.Force11 = roll1;
  EASYCAT.BufferIn.Cust.Force12 = p[0];
  EASYCAT.BufferIn.Cust.Force13 = p[1];
  EASYCAT.BufferIn.Cust.Force14 = p[2];
  EASYCAT.BufferIn.Cust.Force15 = p[3];
  EASYCAT.BufferIn.Cust.Force16 = p[4];
  EASYCAT.BufferIn.Cust.Force17 = p[5];
  EASYCAT.BufferIn.Cust.Force18 = p[6];
  EASYCAT.BufferIn.Cust.Force19 = p[7];
  EASYCAT.BufferIn.Cust.Force20 = AFO_corrected/2/pi*100;
  EASYCAT.BufferIn.Cust.Force21 = uStreamingDataIMU1.sData.lAcc.ax;
  EASYCAT.BufferIn.Cust.Force22 = uStreamingDataIMU1.sData.lAcc.ay;
  EASYCAT.BufferIn.Cust.Force23 = uStreamingDataIMU1.sData.lAcc.az;
}