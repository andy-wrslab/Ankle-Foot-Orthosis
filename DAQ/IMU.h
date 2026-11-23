#ifndef IMU_H
#define IMU_H

#include <TeensyThreads.h>


/////////////////
#define CPU_RESTART_ADDR (uint32_t *)0xE000ED0C
#define CPU_RESTART_VAL 0x5FA0004
#define CPU_RESTART (*CPU_RESTART_ADDR = CPU_RESTART_VAL);
/////////////////


#define TRUE 1
#define FALSE 0

#define MAX_YEI_DATA_PACKET 255

#define DEGTORAD 0.017453f
#define RADTODEG 57.295779f

#define NO_SLOT 255
#define READ_TARED_ORIENTATION_AS_QUATERNION 0
#define READ_TARED_ORIENTATION_AS_EULER_ANGLES 1
#define READ_UNTARED_ORIENTATION_AS_QUATERNION 6
#define READ_UNTARED_ORIENTATION_AS_EULER_ANGLES 7
#define READ_NORMALIZED_ACCELEROMETER_VECTOR 34
#define READ_CORRECTED_GYROSCOPE_VECTOR 38
#define READ_CORRECTED_ACCELEROMETER_VECTOR 39
#define READ_CORRECTED_LINEAR_ACCELERATION 41
#define READ_RAW_GYROSCOPE_VECTOR 65
#define READ_RAW_ACCELEROMETER_VECTOR 66
#define READ_RAW_COMPASS_VECTOR 67

#define CMD_SET_BASE_OFFSET_WITH_CURRENT_ORIENTATION 22
#define CMD_SET_STREAMING_SLOT 80
#define CMD_SET_STREAMING_TIMING 82
#define CMD_GET_STREAMING_BATCH 84
#define CMD_START_STREAMING 85
#define CMD_STOP_STREAMING 86
#define CMD_TARE_WITH_CURRENT_ORIENTATION 96
#define CMD_SET_REFERENCE_VECTOR_MODE 105
#define CMD_SET_COMPASS_ENABLE 109
#define CMD_RESET_FILTER 120
#define CMD_SET_ACCELEROMETER_RANGE 121
#define CMD_SET_FILTER_MODE 123
#define CMD_SET_GYROSCOPE_RANGE 125
#define CMD_SET_COMPASS_RANGE 126

#define CMD_GET_COMPASS_ENABLED_STATE 142
#define CMD_GET_ACCELEROMETER_RANGE 148
#define CMD_GET_FILTER_MODE 152
#define CMD_GET_GYROSCOPE_RANGE 154
#define CMD_GET_COMPASS_RANGE 155
#define CMD_BEGIN_GYROSCOPE_AUTOCALIBRATION 165
#define CMD_SET_CALIBRATION_MODE 169
#define CMD_RESPONSE_HEADER_BITFIELD 221
#define CMD_COMMIT_SETTINGS 225  // 0xE1 - persist current settings to IMU non-volatile memory
#define CMD_SET_UART_BAUD_RATE 231
#define CMD_GET_UART_BAUD_RATE 232
#define CMD_SET_LED_COLOR 238
#define START_SPI_DATA_TRANSFER 0xF6
#define START_NO_RESP_HEADER 0xF7
#define START_RESP_HEADER 0xF9

#define SPI_IDLE_STATE 0x00
#define SPI_READY_STATE 0x01
#define SPI_BUSY_STATE 0x02
#define SPI_ACC_STATE 0x04
#define DELAY_SPI_YEI 5          //[us]
#define DELAY_WAIT_SERIAL_YEI 1  //[us]
#define DELAY_SERIAL_YEI 10      //[us]

#define REFERENCE_VECTOR_SINGLE_STATIC_MODE 0
#define REFERENCE_VECTOR_SINGLE_AUTO_MODE 1
#define REFERENCE_VECTOR_SINGLE_AUTO_CONTINUOUS_MODE 2
#define REFERENCE_VECTOR_MULTI_REFERENCE_MODE 3

#define ACCELEROMETER_RANGE_6G 0  // 2/6g
#define ACCELEROMETER_RANGE_12G 1  // 4/12g
#define ACCELEROMETER_RANGE_24G 2  // 8/24g for HH model 

#define GYROSCOPE_RANGE_250 0
#define GYROSCOPE_RANGE_500 1
#define GYROSCOPE_RANGE_2000 2

#define COMPASS_RANGE_0_8 0
#define COMPASS_RANGE_1_3 1
#define COMPASS_RANGE_1_9 2
#define COMPASS_RANGE_2_5 3
#define COMPASS_RANGE_4_0 4
#define COMPASS_RANGE_4_7 5
#define COMPASS_RANGE_5_6 6
#define COMPASS_RANGE_8_1 7

#define FILTER_IMU 0
#define FILTER_KALMAN 1
#define FILTER_KALMAN_ALTERNATING 2
#define FILTER_COMPLEMENTARY 3
#define FILTER_QUATERNION_GRADIENT_DESCEND 4
#define FILTER_MAGNETORESISTIVE_QUATERNION_GRADIENT_DESCEND 5

#define CALIBRATION_MODE_BIAS 0
#define CALIBRATION_MODE_BIAS_SCALE 1
#define CALIBRATION_MODE_ORTHO 2

#define CMD_SET_AXIS_DIRECTIONS 116
#define AXIS_XR_YF_ZU 0x01  // Right-handed system
#define AXIS_XU_YR_ZF 0x02
#define AXIS_XF_YU_ZR 0x05

#define CMD_GET_FIRMWARE_VERSION 0xDF
#define CMD_GET_HARDWARE_VERSION 0xE6

#define YEI_DELAY_AFTER_COMMAND 100  //[ms]

#define BYTE_USB_PACKET 128
#define BYTE_DATA_PACKET 128
#define BYTE_PUREDATA_PACKET 64       //91 60
#define BYTE_WIFI_INCOMING_PACKET 16  //11//7

uint8_t YEIdataPacket[MAX_YEI_DATA_PACKET];

#define package_Num 300;



//Bread Board
#define IMU1 Serial4



// AFO
// Force20 still sends AFO_corrected/2/pi*100. Nothing in this firmware assigns
// AFO_corrected, so it is always 0 (kept so the Force20 output is unchanged).
const float pi = 3.14159265359f;
float AFO_corrected = 0;

uint8_t write_command_sent = 0;



struct structStreamingTimingInformation {
  unsigned int interval;
  unsigned int duration;
  unsigned int delay;

} sStreamingTime;


struct structComponentLinearAcceleration {
  //Big Endian
  float az;
  float ay;
  float ax;
};

struct structComponentRawAcceleration {
  //Big Endian
  float r_az;
  float r_ay;
  float r_ax;
};

struct structComponentQuaternion {
  //Big Endian
  float qw;
  float qz;
  float qy;
  float qx;
};


struct structEulerAngles {
  //Big Endian
  float roll;
  float yaw;
  float pitch;
};

struct structComponentRawGyro {
  // Big Endian
  float wz;
  float wy;
  float wx;
};

struct structStreamingData {
  //Big Endian
  structComponentRawAcceleration acc;
  structComponentRawGyro gyro;
  structComponentLinearAcceleration lAcc;
  //structEulerAngles eulerAngles;
  structComponentQuaternion q;
};


union unionStreamingData
{
  structStreamingData sData;
  volatile uint8_t vData[sizeof(structStreamingData)];

} uStreamingDataIMU1;


uint8_t calcCRC256(uint8_t* dataPacket, uint8_t nByte)
{
  uint16_t checksum = 0;
  for (uint8_t i = 1; i < nByte; i++)
  {
    checksum += dataPacket[i];
  }

  return (checksum % 256);
}

void waitByteCountFromSerial(HardwareSerial& serial, unsigned int bytecount)
{
  
  while (serial.available() < bytecount)
  {
    // Serial.println("IMU serial: " + String(serial.available()));
    delayMicroseconds(DELAY_WAIT_SERIAL_YEI);
  }
}

void YEIsettingsHeader(HardwareSerial& serial)
{
  // Settings Header
  YEIdataPacket[0] = START_NO_RESP_HEADER;
  YEIdataPacket[1] = CMD_RESPONSE_HEADER_BITFIELD;
  YEIdataPacket[2] = 0x00;
  YEIdataPacket[3] = 0x00;
  YEIdataPacket[4] = 0x00;
  YEIdataPacket[5] = 0x00;
  YEIdataPacket[6] = calcCRC256(YEIdataPacket, 6);
  serial.write(YEIdataPacket, 7);
  delay(YEI_DELAY_AFTER_COMMAND);
}

void YEIwriteCommandNoDelay(HardwareSerial& serial, uint8_t cmd)
{
  YEIdataPacket[0] = START_NO_RESP_HEADER;
  YEIdataPacket[1] = cmd;
  YEIdataPacket[2] = calcCRC256(YEIdataPacket, 2);
  serial.write(YEIdataPacket, 3);
}

void YEIwriteCommand(HardwareSerial& serial, uint8_t cmd)
{
  YEIwriteCommandNoDelay(serial, cmd);
  delay(YEI_DELAY_AFTER_COMMAND);
}

void YEIwriteCommand(HardwareSerial& serial, uint8_t cmd, uint8_t value)
{
  YEIdataPacket[0] = START_NO_RESP_HEADER;
  YEIdataPacket[1] = cmd;
  YEIdataPacket[2] = value;
  YEIdataPacket[3] = calcCRC256(YEIdataPacket, 3);
  serial.write(YEIdataPacket, 4);
  delay(YEI_DELAY_AFTER_COMMAND);
}

uint8_t YEIgetValue(HardwareSerial& serial, uint8_t cmd)
{
  YEIwriteCommand(serial, cmd);
  return serial.read();
}

void YEIsetStreamingTime(HardwareSerial& serial)
{
  // Set Streaming Time

  YEIdataPacket[0] = START_NO_RESP_HEADER;
  YEIdataPacket[1] = CMD_SET_STREAMING_TIMING;

  uint8_t *pointer = (uint8_t*)&sStreamingTime.interval;
  YEIdataPacket[2] = pointer[3];
  YEIdataPacket[3] = pointer[2];
  YEIdataPacket[4] = pointer[1];
  YEIdataPacket[5] = pointer[0];

  pointer = (uint8_t*)&sStreamingTime.duration;
  YEIdataPacket[6] = pointer[3];
  YEIdataPacket[7] = pointer[2];
  YEIdataPacket[8] = pointer[1];
  YEIdataPacket[9] = pointer[0];

  pointer = (uint8_t*)&sStreamingTime.delay;
  YEIdataPacket[10] = pointer[3];
  YEIdataPacket[11] = pointer[2];
  YEIdataPacket[12] = pointer[1];
  YEIdataPacket[13] = pointer[0];

  YEIdataPacket[14] = calcCRC256(YEIdataPacket, 14);
  serial.write(YEIdataPacket, 15);

  //delay(YEI_DELAY_AFTER_COMMAND);
}

void YEIsetStreamingModeNoDelay(HardwareSerial& serial, uint8_t slot1, uint8_t slot2, uint8_t slot3, uint8_t slot4, uint8_t slot5, uint8_t slot6, uint8_t slot7, uint8_t slot8)
{
  // Setting Streaming Mode
  YEIdataPacket[0] = START_NO_RESP_HEADER;
  YEIdataPacket[1] = CMD_SET_STREAMING_SLOT;

  YEIdataPacket[2] = slot1; //1st slot
  YEIdataPacket[3] = slot2; //2nd slot
  YEIdataPacket[4] = slot3; //3rd slot
  YEIdataPacket[5] = slot4; //4th slot
  YEIdataPacket[6] = slot5; //5th slot
  YEIdataPacket[7] = slot6; //6th slot
  YEIdataPacket[8] = slot7; //7th slot
  YEIdataPacket[9] = slot8; //8th slot

  YEIdataPacket[10] = calcCRC256(YEIdataPacket, 10);
  serial.write(YEIdataPacket, 11);
}

void YEIsetStreamingMode(HardwareSerial& serial, uint8_t slot1, uint8_t slot2, uint8_t slot3, uint8_t slot4, uint8_t slot5, uint8_t slot6, uint8_t slot7, uint8_t slot8)
{
  YEIsetStreamingModeNoDelay(serial, slot1, slot2, slot3, slot4, slot5, slot6, slot7, slot8);
  delay(YEI_DELAY_AFTER_COMMAND);
}

// ---------------------------------------------------------------------------
// Byte-slip protection (2026-11-19).
// Replies carry no header or checksum (see YEIsettingsHeader), so the 52 bytes
// read below are trusted blindly. A stray byte on the RX line (touching the IMU
// pins) used to shift every later packet for good: the data was garbage
// (NaN, +/-1e38), yet each packet was "complete", so lastIMUDataTime kept being
// refreshed and the 0.2 s watchdog never re-initialised the IMU.
// Now: (1) stale RX bytes are dropped before every request, (2) a request with
// no full reply in YEI_REQUEST_TIMEOUT_US is abandoned and re-sent, and
// (3) every packet is sanity-checked before it replaces the last good one.
// ---------------------------------------------------------------------------
#define YEI_REQUEST_TIMEOUT_US 10000UL   // reply normally lands within ~3 ms of the request
uint32_t imu_req_t = 0;                  // micros() when the pending request was sent
volatile uint32_t yeiBadPackets = 0;      // replies rejected by YEIpacketLooksValid()
volatile uint32_t yeiRequestTimeouts = 0; // requests abandoned without a full reply

// Drop whatever is waiting in the RX buffer (stale bytes, noise, a partial reply).
static inline void YEIdrainRx(HardwareSerial& serial)
{
  while (serial.available() > 0) {
    serial.read();
  }
}

static inline bool yeiFinite(float v)
{
  return (v == v) && (v < 1.0e30f) && (v > -1.0e30f);  // rejects NaN, +/-Inf and +/-1e38 junk
}

// Plausibility check of one decoded packet. Units: quaternion (unit norm),
// accelerations in g (range set to 24 g in setupIMU), gyro in rad/s (2000 dps = 34.9 rad/s).
bool YEIpacketLooksValid(const structStreamingData& d)
{
  const float f[13] = {d.acc.r_ax, d.acc.r_ay, d.acc.r_az,
                       d.gyro.wx, d.gyro.wy, d.gyro.wz,
                       d.lAcc.ax, d.lAcc.ay, d.lAcc.az,
                       d.q.qw, d.q.qx, d.q.qy, d.q.qz};
  for (uint8_t i = 0; i < 13; ++i) {
    if (!yeiFinite(f[i])) return false;
  }
  for (uint8_t i = 0; i < 3; ++i) {
    if (fabsf(f[i]) > 25.0f) return false;      // corrected accelerometer [g]
    if (fabsf(f[3 + i]) > 36.0f) return false;  // gyro [rad/s]
    if (fabsf(f[6 + i]) > 25.0f) return false;  // linear acceleration [g]
  }
  const float n2 = d.q.qw * d.q.qw + d.q.qx * d.q.qx + d.q.qy * d.q.qy + d.q.qz * d.q.qz;
  return (n2 > 0.81f) && (n2 < 1.21f);          // |q| within 0.9 .. 1.1
}

// Polling mode
// Returns true only when a complete, valid packet was parsed this call.
bool YEIgetStreamingBatch(unionStreamingData& uStreamingDataIMU1)
{
  int nPacketStreamingData = sizeof(uStreamingDataIMU1);

  if (!write_command_sent) {
    // A new reply is requested only after the previous one was consumed, so any
    // byte still waiting here is stale or noise: drop it so the reply starts at
    // byte 0 of tmpBuf. This alone re-aligns the stream on every poll.
    YEIdrainRx(IMU1);
    YEIwriteCommandNoDelay(IMU1, CMD_GET_STREAMING_BATCH);
    write_command_sent = 1;
    imu_req_t = micros();
  }

  // Bounded wait for the rest of the packet to arrive (max ~800 us)
  if (IMU1.available() > 0 && IMU1.available() < nPacketStreamingData) {
    uint32_t waitStart = micros();
    while (IMU1.available() < nPacketStreamingData) {
      if ((micros() - waitStart) > 800) {
        break;
      }
      delayMicroseconds(DELAY_WAIT_SERIAL_YEI);
    }
  }

  // if(IMU1.available() < nPacketStreamingData)
  // {
  //   // Serial.println("waiting: " + IMU1.available());
  //   // Serial.print("\t");
  //   // Serial.println(IMU1.available());
  //   // delayMicroseconds(DELAY_WAIT_SERIAL_YEI);
  //   // delayNanoseconds(DELAY_WAIT_SERIAL_YEI);
  //   delay(1);
  //   // threads.delay(DELAY_WAIT_SERIAL_YEI);
  //   // return;
  // }
  // delay(4);

  // Serial.println("waiting: " + IMU1.available());

  if(IMU1.available() >= nPacketStreamingData) {
    // Fast bulk read to minimize CPU time and jitter, preserving original byte order
    uint8_t tmpBuf[sizeof(uStreamingDataIMU1)];
    size_t readCount = IMU1.readBytes(tmpBuf, nPacketStreamingData);
    if (readCount == (size_t)nPacketStreamingData) {
      // Decode into a temporary first; the caller's packet (the last good one,
      // which is what goes out on EtherCAT) is only replaced by a valid packet.
      unionStreamingData candidate;
      for (int i = 0; i < nPacketStreamingData; ++i) {
        candidate.vData[nPacketStreamingData - i - 1] = tmpBuf[i];
      }
      write_command_sent = 0;
      if (!YEIpacketLooksValid(candidate.sData)) {
        // Misaligned or corrupted: keep the last good values, drop the rest of
        // this reply, and let the next poll re-request. lastIMUDataTime is not
        // refreshed (we return false), so if it stays bad for 0.2 s the
        // existing watchdog in loop() still re-initialises the IMU.
        yeiBadPackets++;
        YEIdrainRx(IMU1);
        return false;
      }
      uStreamingDataIMU1.sData = candidate.sData;
      return true;   // a complete, valid packet was parsed
    }
  }

  // Lost or late reply (e.g. a dropped byte leaves 51 bytes forever): give up
  // on this request after YEI_REQUEST_TIMEOUT_US and ask again, instead of
  // waiting for the 0.2 s watchdog re-init.
  if (write_command_sent && (uint32_t)(micros() - imu_req_t) > YEI_REQUEST_TIMEOUT_US) {
    yeiRequestTimeouts++;
    YEIdrainRx(IMU1);
    write_command_sent = 0;
  }

  return false;      // no complete valid packet this call
}


void quaternion2euler(float q0, float q1, float q2, float q3, float& phi, float& theta, float& psi)
{
  //quaternConj(q0,q1,q2,q3);

  q1 = -q1;
  q2 = -q2;
  q3 = -q3;

  float R11 = 2 * q0 * q0 - 1 + 2 * q1 * q1;
  float R21 = 2 * (q1 * q2 - q0 * q3);
  float R31 = 2 * (q1 * q3 + q0 * q2);
  float R32 = 2 * (q2 * q3 - q0 * q1);
  float R33 = 2 * q0 * q0 - 1 + 2 * q3 * q3;

  phi = atan2(R32, R33);
  theta = -atan(R31 / sqrt(1 - R31 * R31) );
  psi = atan2(R21, R11 );
}


#endif