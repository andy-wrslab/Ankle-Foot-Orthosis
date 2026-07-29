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
const int     READ_IMU_INTERVAL   = 2000; // [250Hz]
const int   FILTER_TIMER_INTERVAL = 1000; // [1kHz]
const int  EASYCAT_TIMER_INTERVAL = 500; // [2kHz]


const int             NUM_SENSORS = 6;
const int             PNTS_TO_AVG = 5;
unsigned int           ADC_cycles = 0; 
unsigned long             t_blink = 0;
bool                   led_status = 0;
bool          infrared_led_status = 0;
int        infrared_led_wait_time = 1;
unsigned long               t_LED = 0;   // last IR-LED toggle time [ms]

volatile int          raw_encoder = 0;
volatile float    encoder_reading = 0;
volatile float        pot_reading = 0;
volatile float      heel_pressure = 0;

volatile bool imu_poll_due = false;
volatile bool easycat_poll_due = false;
volatile bool sensors_poll_due = false;
volatile bool filter_poll_due = false;

EasyCAT                   EASYCAT(10);
SensorData       sensors[NUM_SENSORS];   // {potentiometer, encoder, pressure, velocity}
IntervalTimer        readSensorsTimer;
IntervalTimer        readIMUTimer; 
IntervalTimer      filterSensorsTimer;
IntervalTimer      easyCatTimer;



// ---------------------------------------------------------------------------
// EasyCAT timing
//
// EasyCAT::MainTask() should not be called from an interrupt, because the SPI
// transaction temporarily disables interrupts which will block other
// peripherals such as Serial4.  We therefore call sendEasyCatData() from the
// main loop at a fixed interval.  This variable holds the last time (in
// microseconds) that sendEasyCatData() was executed.
static unsigned long lastEasyCatTime = 0;

uint8_t nPacketStreamingData = sizeof(structStreamingData);
boolean reset_imu;
boolean sig;

// IMU watchdog: time (us) of the last valid IMU packet, plus the silence
// timeout after which loop() requests a fast re-init.  This lets the IMU be
// unplugged mid-test and resume streaming on its own once reconnected, without
// redoing calibration/tare (the committed init values are reused).
unsigned long lastIMUDataTime = 0;
const unsigned long IMU_TIMEOUT_US = 200000UL;   // 0.2 s

unsigned long nowTime = 0;
unsigned long startTime;
float yaw1, pitch1, roll1;
bool easycat_enabled = true; // enable EasyCAT for timing verification
bool sensors_enabled = true; // enable sensors timing for interval verification
bool filter_enabled = true;  // enable filter so sensors[x].filtered_value updates

uint16_t p[] = {0, 0, 0, 0, 0, 0, 0, 0};
uint16_t p_sum[] = {1000, 1000}; // sum all the pressure
uint16_t p_sum_0_filt = 0;
uint16_t p_sum_1_filt = 0;
uint16_t p_heel = 0;
uint16_t p_toe = 0;
volatile uint32_t t_IMU = 0;

#define PIN_INFRARED_LED 14


void  setup() {
  Serial.begin(921600);
  setupLED();
  setupEASYCAT();
  setupSensors();
  setupIMU();
  setupTimers();
  
}


float ax_prev = -100;
float ax_curr = -100;
void  loop() {
  // IMU watchdog: if no valid packet for > IMU_TIMEOUT_US, request a fast
  // re-init so a disconnected then reconnected IMU resumes streaming on its own.
  if (micros() - lastIMUDataTime > IMU_TIMEOUT_US) {
    reset_imu = false;            // next readIMU() runs the fast re-init path
    lastIMUDataTime = micros();   // don't re-trigger every iteration
  }

  // Prioritize IMU read to minimize latency
  if (imu_poll_due) {
    imu_poll_due = false;
    readIMU();                                // <-- contains UART I/O, quaternion2euler, etc.
  }

  // Opportunistically read all available full IMU packets to avoid waiting for next poll
  int packetsRead = 0;
  while (IMU1.available() >= nPacketStreamingData && packetsRead < 3) {
    readIMU();
    packetsRead++;
  }

  // Periodically handle other work without using interrupts.
  if (sensors_enabled && sensors_poll_due) {
    sensors_poll_due = false;
    readSensors();

    // // Debug: track potentiometer read interval (readSensors cadence)
    // static uint32_t pot_last_ts = 0;
    // static uint32_t pot_sum_50 = 0;
    // static uint32_t pot_count = 0;
    // uint32_t pot_now = micros();
    // if (pot_last_ts != 0) {
    //   uint32_t dt = pot_now - pot_last_ts;
    //   pot_sum_50 += dt;
    //   pot_count++;
    //   if ((pot_count % 50) == 0) {
    //     Serial.print("POT dt50(us): ");
    //     Serial.print(pot_sum_50); // expect ~10000 us if running at 5kHz (50 * 200us)
    //     Serial.print(" avg(us): ");
    //     Serial.println(pot_sum_50 / 50); // expect ~200 us
    //     pot_sum_50 = 0;
    //   }
    // }
    // pot_last_ts = pot_now;
  }

  if (filter_enabled && filter_poll_due) {
    filter_poll_due = false;
    filterSensors();
  }

  if (easycat_enabled && easycat_poll_due) {
    easycat_poll_due = false;
    application();
    EASYCAT.MainTask();

    // // Debug: track EasyCAT execution interval aiming for 2kHz
    // static uint32_t ec_last_ts = 0;
    // static uint32_t ec_sum_10 = 0;
    // static uint32_t ec_count = 0;
    // uint32_t ec_now = micros();
    // if (ec_last_ts != 0) {
    //   uint32_t dt = ec_now - ec_last_ts;
    //   ec_sum_10 += dt;
    //   ec_count++;
    //   if ((ec_count % 10) == 0) {
    //     Serial.print("EC dt10(us): ");
    //     Serial.print(ec_sum_10); // expect ~5000 us if running at 2kHz
    //     Serial.print(" avg(us): ");
    //     Serial.println(ec_sum_10 / 10); // expect ~500 us
    //     ec_sum_10 = 0;
    //   }
    // }
    // ec_last_ts = ec_now;
  }

  // Toggle the infrared LED at a random 1-3 s interval (external sync marker).
  // Non-blocking; a new random wait is chosen on each toggle.
  if (millis() - t_LED > 1000 * (unsigned long)infrared_led_wait_time) {
    infrared_led_status = !infrared_led_status;
    digitalWrite(PIN_INFRARED_LED, infrared_led_status);
    infrared_led_wait_time = random(3) + 1;   // 1, 2, or 3 seconds
    t_LED = millis();
    Serial.print("LED STATUS: ");
    Serial.println(infrared_led_status);
  }

  // Minimal debug print to verify update timing
  ax_curr = uStreamingDataIMU1.sData.lAcc.ax;
  ax_curr = sensors[0].filtered_value;
  // ax_curr = sensors[0].value;
  if (ax_prev != ax_curr) {
    ax_prev = ax_curr;
    Serial.print(ax_prev);
    Serial.print(" -> ");
    Serial.println(micros());
  }
  
}



void  setupLED() {
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_INFRARED_LED, OUTPUT);
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


void readIMU_ISR() { imu_poll_due = true; }
void sendEasyCatData_ISR() {
  easycat_poll_due = true;
}
void readSensors_ISR() { sensors_poll_due = true; }
void filterSensors_ISR() { filter_poll_due = true; }

void  setupTimers() {

  easyCatTimer.priority(255);
  readSensorsTimer.priority(224);
  filterSensorsTimer.priority(232);
  readIMUTimer.priority(200);



  // Do not run EasyCAT::MainTask() from an interrupt.  The SPI transaction
  // disables interrupts long enough to starve the UART used by the IMU.  We
  // will instead invoke sendEasyCatData() periodically from loop().
  if (easycat_enabled) {
    easyCatTimer.begin(sendEasyCatData_ISR, EASYCAT_TIMER_INTERVAL);
  }
  if (sensors_enabled) {
    readSensorsTimer.begin(readSensors_ISR, READ_TIMER_INTERVAL);
  }
  if (filter_enabled) {
    filterSensorsTimer.begin(filterSensors_ISR, FILTER_TIMER_INTERVAL);
  }
  readIMUTimer.begin(readIMU_ISR, READ_IMU_INTERVAL);
  readIMUTimer.priority(64); // raise priority of IMU flag ISR
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
    // num = 1; // !!!
    digitalWrite(PIN_A, (num & (1 << 1)) ? HIGH : LOW); // Set PIN_A based on bit 1
    digitalWrite(PIN_B, (num & (1 << 0)) ? HIGH : LOW); // Set PIN_B based on bit 0
    digitalWrite(PIN_C, (num & (1 << 2)) ? HIGH : LOW); // Set PIN_C based on bit 2

    delayMicroseconds(4);
    return analogRead(PIN_PRESSURE);
}

void sendEasyCatData() {
  // Serial.println("sendEasyCatData");
  application();
  EASYCAT.MainTask();
}

void setupIMU() {
  IMU1.begin(921600);
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
  YEIwriteCommandNoDelay(IMU1, CMD_TARE_WITH_CURRENT_ORIENTATION);  // set reference once, here
  YEIwriteCommandNoDelay(IMU1, CMD_RESET_FILTER);
  delay(1000);
  // Stream full payload to match structStreamingData (quat + lin acc + gyro + raw acc)
  YEIsetStreamingMode(IMU1, READ_TARED_ORIENTATION_AS_QUATERNION, READ_CORRECTED_LINEAR_ACCELERATION, READ_CORRECTED_GYROSCOPE_VECTOR, READ_CORRECTED_ACCELEROMETER_VECTOR, NO_SLOT, NO_SLOT, NO_SLOT, NO_SLOT);

  // sStreamingTime.interval = 2000; //10000; //[us]
  sStreamingTime.interval = 4000; //10000; //[us]
  sStreamingTime.duration = 0xFFFFFFFF;
  sStreamingTime.delay = 0;  //[us]
  YEIsetStreamingTime(IMU1);
  YEIwriteCommand(IMU1, CMD_COMMIT_SETTINGS);   // persist calibration + tare to IMU flash
  IMU1.flush();
  reset_imu = TRUE;             // calibration/tare done above -> just stream and read
  sig = FALSE;
  startTime = micros();
  lastIMUDataTime = startTime;  // arm the watchdog
}

void readIMU() {
  // Serial.println("fetchingIMUData");

  if (!reset_imu)
  {
    // Fast re-init path (triggered by the watchdog after an IMU dropout).
    // No re-calibration and no re-tare here, so the committed reference
    // orientation is preserved across a disconnect/reconnect.
    reset_imu = true;

    YEIwriteCommandNoDelay(IMU1, CMD_STOP_STREAMING);
    IMU1.flush();

    // Discard any stale/partial bytes still sitting in the RX buffer from
    // before the dropout.  IMU1.flush() only drains the TX side, so without
    // this the first batch after a reconnect can be byte-misaligned.
    while (IMU1.available()) { IMU1.read(); }

    // Stream full payload to match structStreamingData (quat + lin acc + gyro + raw acc)
    YEIsetStreamingMode(IMU1, READ_TARED_ORIENTATION_AS_QUATERNION, READ_CORRECTED_LINEAR_ACCELERATION, READ_CORRECTED_GYROSCOPE_VECTOR, READ_CORRECTED_ACCELEROMETER_VECTOR, NO_SLOT, NO_SLOT, NO_SLOT, NO_SLOT);
    IMU1.flush();
    YEIsetStreamingTime(IMU1);

    // Clear the on-demand request latch.  YEIgetStreamingBatch() only sends a
    // new CMD_GET_STREAMING_BATCH when this is 0; a dropout leaves it stuck at
    // 1 (request sent, reply never arrived), so without this reset no further
    // requests go out and the IMU never resumes after reconnect.
    write_command_sent = 0;

    lastIMUDataTime = micros();   // give the link time to come back before re-triggering
    sig = !sig;
  }
  else
  {
    // Read IMU data; only a fully-parsed packet counts as "alive".
    if (YEIgetStreamingBatch(uStreamingDataIMU1)) {
      if (easycat_enabled) {
        quaternion2euler(uStreamingDataIMU1.sData.q.qw, uStreamingDataIMU1.sData.q.qy, uStreamingDataIMU1.sData.q.qz, uStreamingDataIMU1.sData.q.qx, yaw1, pitch1, roll1);
      }
      lastIMUDataTime = micros();
    }
  }
}


void readAllPressure() {
    p_sum[0] = p_sum[1];
    p_sum[1] = 0;
    // // Read Pressure
    for (uint8_t h = 0; h < 8; h++) {
      p[h] = readPressure(h+1);
      p_sum[1] = p_sum[1] + p[h];
    }

    p_heel = (p[1] + p[6] + p[7])/3;
    p_toe = max( max( max( max(p[0], p[2]), p[3] ), p[4] ), p[5] );

}

void  readSensors() {

  pot_reading = readADChannel(CH_NUM_LC);
  encoder_reading = readEncoder();
  readAllPressure();

  sensors[0].sum += pot_reading;      // read potentiometer
  sensors[1].sum += encoder_reading;                    // read encoder
  sensors[2].sum += p_heel; // read pressure
  sensors[3].sum += p_toe; // read pressure
  sensors[4].sum += p_sum[0]; // read pressure
  sensors[5].sum += p_sum[1]; // read pressure

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
    p_sum_0_filt = p_sum_1_filt;
    p_sum_1_filt = sensors[4].filtered_value;
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
    EASYCAT.BufferIn.Cust.Force24 = uStreamingDataIMU1.sData.gyro.wx;
    EASYCAT.BufferIn.Cust.Force25 = uStreamingDataIMU1.sData.gyro.wy;
    EASYCAT.BufferIn.Cust.Force26 = uStreamingDataIMU1.sData.gyro.wz;
    EASYCAT.BufferIn.Cust.Force27 = uStreamingDataIMU1.sData.acc.r_ax;
    EASYCAT.BufferIn.Cust.Force28 = uStreamingDataIMU1.sData.acc.r_ay;
    EASYCAT.BufferIn.Cust.Force29 = uStreamingDataIMU1.sData.acc.r_az;
    EASYCAT.BufferIn.Cust.Force30 = infrared_led_status;

    // Debugging output has been removed from this function.  Printing inside
    // application() previously caused long delays, especially when called from
    // an interrupt.  If you need to monitor the IMU data, do it from loop().

    // Serial.print(0);
    // Serial.print(" -> ");
    // Serial.println(micros());
    Serial.println(readEncoder());
    
    // for (int i = 0; i < 8; i++) {
    //   Serial.print("p" + String(i) + ": " + String(p[i]) + "  \t");
    // }
    // Serial.println();
    // Serial.println("ax: " + String(uStreamingDataIMU1.sData.lAcc.ax) + "\t");
    // Serial.print("ay: " + String(uStreamingDataIMU1.sData.lAcc.ay) + "\t");
    // Serial.print("az: " + String(uStreamingDataIMU1.sData.lAcc.az) + "\t");
    // Serial.print("gx: " + String(uStreamingDataIMU1.sData.gyro.wx) + "\t");
    // Serial.print("gy: " + String(uStreamingDataIMU1.sData.gyro.wy) + "\t");
    // Serial.print("gz: " + String(uStreamingDataIMU1.sData.gyro.wz) + "\t");
    // Serial.print("ax: " + String(uStreamingDataIMU1.sData.acc.r_ax) + "\t");
    // Serial.print("ay: " + String(uStreamingDataIMU1.sData.acc.r_ay) + "\t");
    // Serial.print("az: " + String(uStreamingDataIMU1.sData.acc.r_az) + "\t");
    // Serial.println();

}