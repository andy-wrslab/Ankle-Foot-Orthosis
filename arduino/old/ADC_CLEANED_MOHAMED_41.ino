///// TORQUE TRANSDUCER AND EASYCA-3/23/2023//////// 

#define CUSTOM 
#include "teensySensoryMB.h" 
#include "EasyCAT.h"
#include <SPI.h>
#include <Encoder.h>
#include "SensorData.h"
#include "Utilities.h"
#include "Timer.h"  // Include the new Timer header

#define PIN_ENABLE 25
#define PIN_A      22
#define PIN_B      21
#define PIN_C      20
#define PIN_PRESSURE A15

// ADC channels 
const byte  CH_NUM_LC_1 = 1;

// Timers intervals 
const uint16_t ADC_TIMER_INTERVAL    =  200;       //[.us]
const uint16_t FILTER_TIMER_INTERVAL =  1000;      //[kHz]

// Variables 
const uint16_t  PNTS_TO_AVG = 5;                // Average points to read 

// Filter - properties: Butterworth, 2nd order, 12 HZ passband
const double a_lc[] = {1.0,  -1.911197067426073, 0.914975834801433};
const double b_lc[] = {0.0009446918438401619,   0.001889383687680, 0.0009446918438401619};

unsigned long t = 0;
unsigned long t0 = 0;
unsigned long delta_t = 0;

uint16_t raw_encoder = 0;
float degAngle = 0; // Angle in degrees

uint16_t command = 0b1111111111111111; // read command (0xFFF)

double encoder_previous = 0.0;
double encoder_current = 0.0;

unsigned long prevMillis = 0;
unsigned long currentMillis = 0;
unsigned long blinkInterval = 1000;
bool led_status = true;
int count = 0;

// EasyCAT 
EasyCAT  EASYCAT(10);

// Timers instances 
IntervalTimer ADCTimer;
IntervalTimer FilterTimer;

const int LED_GREEN = 5;

// Instantiate sensor objects with descriptive names
PotentiometerSensor potentiometer(CH_NUM_LC_1);  // Pass ADC channel number
EncoderSensor encoder(&encoder_current);         // Pass pointer to encoder_current
FsrSensor fsr;
VelocitySensor velocity(&pot_reading_prev, &pot_reading_curr);

// Create an array of SensorData pointers
Sensor* sensors[] = { &potentiometer, &encoder, &fsr, &velocity };
int numSensors = sizeof(sensors) / sizeof(sensors[0]);

void setup() {
  Serial.begin(9600);
  setupADC();
  ADCTimer.begin(functionADCTimer, ADC_TIMER_INTERVAL);
  FilterTimer.begin(functionFilterTimer, FILTER_TIMER_INTERVAL);

  Serial.print ("\nEasyCAT - Generic EtherCAT slave\n");

  SPI1.begin();
  pinMode(CS_pin, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);

  // Initialize the EasyCAT board
  if (EASYCAT.Init() == true) {
    Serial.print ("initialized");
  } else {
    Serial.print ("initialization failed");
  }

  digitalWrite(LED_GREEN, HIGH);

  pinMode(PIN_A, OUTPUT);
  pinMode(PIN_B, OUTPUT);
  pinMode(PIN_C, OUTPUT);

  // Initialize sensor names
  potentiometer.name = "potentiometer";
  encoder.name = "encoder";
  fsr.name = "fsr";
  velocity.name = "velocity";

  encoder_current = readRegister();
  encoder_previous = encoder_current;
}

void loop() {
  t = millis();
  delta_t = t - t0;

  EASYCAT.MainTask();

  if (delta_t >= 1) {
    t0 = t;
    Application();
  }

  currentMillis = millis();
  if (currentMillis - prevMillis >= blinkInterval) {
    prevMillis = currentMillis;

    if (!(count % 500)) {
      led_status = !led_status;
      digitalWrite(LED_GREEN, led_status);
    }
    count++;
  }
}

void Application() {
  EASYCAT.BufferIn.Cust.Force1 = potentiometer.filtered;
  EASYCAT.BufferIn.Cust.Force2 = encoder.filtered;
  EASYCAT.BufferIn.Cust.Force3 = fsr.filtered;
  // If needed, send velocity data as well
  // EASYCAT.BufferIn.Cust.Velocity = velocity.filtered;
}

// Remove the definitions of functionADCTimer and functionFilterTimer from this file