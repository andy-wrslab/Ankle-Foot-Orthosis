#define CUSTOM

#include <SPI.h>
#include <Encoder.h>

// Include the EasyCAT library
#include "EasyCAT/EasyCAT.h"

// Include sensor and utility headers
#include "sensors/SensorData.h"
#include "sensors/PotentiometerSensor.h"
#include "sensors/EncoderSensor.h"
#include "sensors/FsrSensor.h"
#include "sensors/VelocitySensor.h"
#include "utilities/Utilities.h"
#include "utilities/Timer.h"


// Timer intervals
const uint16_t ADC_TIMER_INTERVAL    =  200;   // [µs]
const uint16_t FILTER_TIMER_INTERVAL = 1000;   // [µs]

unsigned long lastApplicationTime = 0;
unsigned long lastBlinkTime = 0;
const unsigned long applicationInterval = 1;  // Interval for Application() [ms]
const unsigned long blinkInterval = 1000;     // Interval for blinking LED [ms]
bool led_status = true;
int count = 0;


// EasyCAT
EasyCAT EASYCAT(10);

// Timer instances
IntervalTimer ADCTimer;
IntervalTimer FilterTimer;

const int LED_GREEN = 5;

// Variables used by sensors
extern volatile int16_t pot_reading_prev;
extern volatile int16_t pot_reading_curr;

// Instantiate sensor objects
PotentiometerSensor potentiometer;
EncoderSensor encoder;
FsrSensor fsr;
VelocitySensor velocity(&pot_reading_prev, &pot_reading_curr);

// Create an array of SensorData pointers
Sensor* sensors[] = { &potentiometer, &encoder, &fsr, &velocity };
int numSensors = sizeof(sensors) / sizeof(sensors[0]);

void setup() {
  Serial.begin(9600);
  setupADC();

  SPI1.begin();
  pinMode(CS_pin, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);


  Serial.println("\nEasyCAT - Generic EtherCAT slave");
  // Initialize the EasyCAT board
  if (EASYCAT.Init() == true) {
    Serial.println("initialized");
  } else {
    Serial.println("initialization failed");
  }

  digitalWrite(LED_GREEN, HIGH);

  // Initialize pressure sensor selection pins
  pinMode(PIN_A, OUTPUT);
  pinMode(PIN_B, OUTPUT);
  pinMode(PIN_C, OUTPUT);


  // Start the timers (ensure they are started after variable initializations)
  ADCTimer.begin(functionADCTimer, ADC_TIMER_INTERVAL);
  FilterTimer.begin(functionFilterTimer, FILTER_TIMER_INTERVAL);
}

void loop() {
  unsigned long currentMillis = millis();

  // Run EASYCAT MainTask
  EASYCAT.MainTask();



  // Run Application() every 'applicationInterval' milliseconds
  if (currentMillis - lastApplicationTime >= applicationInterval) {
    lastApplicationTime = currentMillis;
    Application();
  }

  // Blink LED every 'blinkInterval' milliseconds
  if (currentMillis - lastBlinkTime >= blinkInterval) {
    lastBlinkTime = currentMillis;

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