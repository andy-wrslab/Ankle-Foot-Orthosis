/*
 * ADC, clock at 72 MHz
 */
#define CUSTOM
#include "TeensySlaveMB2.h"
#include "EasyCat.h"
#include <SPI.h>
//EasyCAT EASYCAT(10);

////////    ADC   ////////
#define CONVST   38
#define SCLK     37
#define TFS      36
#define RFS      35
#define DATAIN   34
#define DATAOUT  33

// CLOCK AT 72 MHZ!!!!!!!!!!!
//
#define SCLK_DELAY      0.25f              
#define CONVST_DELAY    6                  
#define RW_DELAY        0.5f
//
#define ADC_TIMER_INTERVAL      200       //[.us]
#define FILTER_TIMER_INTERVAL   1000      //[kHz]
#define PNTS_TO_AVG 5
//
IntervalTimer ADCTimer;
IntervalTimer FilterTimer;

const byte CH_NUM_LC_1 = 1;
const byte CH_NUM_LC_2 = 2;
const byte CH_NUM_LC_3 = 3;
const byte CH_NUM_LC_4 = 4;
//const byte CH_NUM_LC_5 = 5;
//const byte CH_NUM_LC_6 = 6;

volatile unsigned long ADC_cycles = 0;

float LC_1_local;
float LC_2_local;
float LC_3_local;
float LC_4_local;

volatile long sum_LC_1 = 0;
volatile long sum_LC_2 = 0;
volatile long sum_LC_3 = 0;
volatile long sum_LC_4 = 0;

volatile float LC_1_f = 0.0f;
volatile float LC_2_f = 0.0f;
volatile float LC_3_f = 0.0f;
volatile float LC_4_f = 0.0f;

volatile float LC_1 = 0.0f;
volatile float LC_2 = 0.0f;
volatile float LC_3 = 0.0f;
volatile float LC_4 = 0.0f;

volatile float LC_1_raw = 0.0f;
volatile float LC_2_raw = 0.0f;
volatile float LC_3_raw = 0.0f;
volatile float LC_4_raw = 0.0f;


// FILTER
// Butterworth, 2nd order, 10Hz passband-
const float a_lc[] = {1.000000000000000f,  -1.911197067426073f,  0.914975834801433f};
const float b_lc[] = {0.0009446918438401619f, 0.001889383687680f, 0.0009446918438401619f};
// Elliptic, 1st order, 10Hz passband
//const float a_lc[] = {1.000000000000000f, -0.885223934281153f};
//const float b_lc[] = {0.057388032859424f,   0.057388032859424f};

volatile float LC_1_buff_raw[] = {0.0f, 0.0f, 0.0f, 0.0f};
volatile float LC_1_buff_filt[] = {0.0f, 0.0f, 0.0f, 0.0f};
volatile float LC_2_buff_raw[] = {0.0f, 0.0f, 0.0f, 0.0f};
volatile float LC_2_buff_filt[] = {0.0f, 0.0f, 0.0f, 0.0f};
volatile float LC_3_buff_raw[] = {0.0f, 0.0f, 0.0f, 0.0f};
volatile float LC_3_buff_filt[] = {0.0f, 0.0f, 0.0f, 0.0f};
volatile float LC_4_buff_raw[] = {0.0f, 0.0f, 0.0f, 0.0f};
volatile float LC_4_buff_filt[] = {0.0f, 0.0f, 0.0f, 0.0f};

int16_t rawDataADC;

int16_t ADC_data;

float pi = 3.14159265f;

unsigned long t1;
unsigned long t;
unsigned long t0 = 0;
unsigned long delta_t;

/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

void setup()
{
  Serial.begin(9600);
  setupADC();
  ADCTimer.begin(functionADCTimer, ADC_TIMER_INTERVAL);
  FilterTimer.begin(functionFilterTimer, FILTER_TIMER_INTERVAL);

  Serial.print ("\nEasyCAT - Generic EtherCAT slave\n");          // print the banner
                                     //
  //Serial.print ("initialized");                                 //

                                                              //---- initialize the EasyCAT board -----
 /*                                                                
  if (EASYCAT.Init() == true)                                     // initialization
  {                                                               // succesfully completed
    Serial.print ("initialized");                                 //
  }                                                               //
 
  else                                                            // initialization failed  
  {                                                               // the EasyCAT .oard was not recognized
    Serial.print ("initialization failed");                       //    
   */                                                               // The most common reason is that the SPI
                                                                  // chip select choosen on the board doesn't
                                                                  // match the one choosen by the firmware
                                                                 
    pinMode(13, OUTPUT);                                          // stay in loop for ever        
//    digitalWrite (13, HIGH);                                    //  
//    while(1)                                                      //
//    {    
//      LC_1_local = (long) (readADChannel(CH_NUM_LC_1));
//      LC_2_local = (long) (readADChannel(CH_NUM_LC_2));
//
//      int input_val_1 = readADChannel(CH_NUM_LC_1);
//      // int input_val_2 = readADChannel(CH_NUM_LC_2);
//      Serial.print(input_val_1);
//      Serial.println("");//  
//
//
////          LC_3_local = (long) (readADChannel(CH_NUM_LC_3));
////          LC_4_local = (long) (readADChannel(CH_NUM_LC_4));
////          Serial.print(LC_1_local);
////          Serial.print(", ");
////          Serial.print(LC_2_local);
////          Serial.print(", ");
////          Serial.print(LC_3_local);
////          Serial.print(", ");
////          Serial.println(LC_2_local);
//          delay(500);
//
//                                              //
//    }                                                             //
  }
 
//  PreviousMillis = millis();
                                // execute the EasyCAT task
}

void loop()
{
  t = millis();
  t1 = micros();
  delta_t = t - t0;
 
  noInterrupts();
  LC_1_local = LC_1_f;
  LC_2_local = LC_2_f;
  LC_3_local = LC_3_f;
  LC_4_local = LC_4_f;
  interrupts();
 
//EASYCAT.MainTask();

if (delta_t >= 1)
 {
    t0 = t;
    Serial.print(LC_1_local);
    Serial.print(", ");
    Serial.print(LC_2_local);
    Serial.print(", ");
    Serial.print(LC_3_local);
    Serial.print(", ");
    Serial.println(LC_4_local);

//    Serial.print(LC_1_raw);
//    Serial.print(", ");
//    Serial.print(LC_2_raw);
//    Serial.print(", ");
//    Serial.print(LC_3_raw);
//    Serial.print(", ");
//    Serial.println(LC_4_raw);

//  uint16_t indata;
//  bitWrite(indata, 4, digitalRead(DATAIN));
//Serial.println(indata);
   
//Application();
}
                                          // user applications
}

/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////


void Application ()                                        
{  
  EASYCAT.BufferIn.Cust.Force1 = LC_1_local;
  EASYCAT.BufferIn.Cust.Force2 = LC_2_local;
  EASYCAT.BufferIn.Cust.Force3 = LC_3_local;
  EASYCAT.BufferIn.Cust.Force4 = LC_4_local;
}
 



/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////




/////////////////////        Function ADC Timer        ///////////////////
void functionADCTimer()
{


  sum_LC_1 += (long) (readADChannel(CH_NUM_LC_1));
  sum_LC_2 += (long) (readADChannel(CH_NUM_LC_2));
  sum_LC_3 += (long) (readADChannel(CH_NUM_LC_3));
  sum_LC_4 += (long) (readADChannel(CH_NUM_LC_4));
 
 

  ADC_cycles++;
  if (ADC_cycles == PNTS_TO_AVG)
  {
     
    LC_1_raw = ((float) (sum_LC_1)) / PNTS_TO_AVG;
    LC_2_raw = ((float) (sum_LC_2)) / PNTS_TO_AVG;
    LC_3_raw = ((float) (sum_LC_3)) / PNTS_TO_AVG;
    LC_4_raw = ((float) (sum_LC_4)) / PNTS_TO_AVG;

    ///// Load cell calibration 3.0 convert LC readings to Newton /////

    LC_1 = - 0.0420747f * LC_1_raw;//0.406
    LC_2 = + 0.0395213f * LC_2_raw; //new
    LC_3 = -0.04139 * LC_3_raw; // new one
    LC_4 = + 0.0444f * LC_4_raw;//0.0471

    ADC_cycles = 0;

    sum_LC_1 = 0;
    sum_LC_2 = 0;
    sum_LC_3 = 0;
    sum_LC_4 = 0;
  }
}

void functionFilterTimer()
{

  ////// FILTER /////
  int i;
  // compute filtered outputs

  noInterrupts();
  LC_1_f = b_lc[0] * LC_1;
  LC_2_f = b_lc[0] * LC_2;
  LC_3_f = b_lc[0] * LC_3;
  LC_4_f = b_lc[0] * LC_4;

  interrupts();

  for (i = 1; i < 3; i++)
  {
    LC_1_f += b_lc[i] * LC_1_buff_raw[i - 1] - a_lc[i] * LC_1_buff_filt[i - 1];
    LC_2_f += b_lc[i] * LC_2_buff_raw[i - 1] - a_lc[i] * LC_2_buff_filt[i - 1];
    LC_3_f += b_lc[i] * LC_3_buff_raw[i - 1] - a_lc[i] * LC_3_buff_filt[i - 1];
    LC_4_f += b_lc[i] * LC_4_buff_raw[i - 1] - a_lc[i] * LC_4_buff_filt[i - 1];
  }
  // update buffers
  for (i = 3; i > 0; i--)
  {
    LC_1_buff_raw[i] = LC_1_buff_raw[i - 1];
    LC_1_buff_filt[i] = LC_1_buff_filt[i - 1];

    LC_2_buff_raw[i] = LC_2_buff_raw[i - 1];
    LC_2_buff_filt[i] = LC_2_buff_filt[i - 1];

    LC_3_buff_raw[i] = LC_3_buff_raw[i - 1];
    LC_3_buff_filt[i] = LC_3_buff_filt[i - 1];

    LC_4_buff_raw[i] = LC_4_buff_raw[i - 1];
    LC_4_buff_filt[i] = LC_4_buff_filt[i - 1];
  }
  LC_1_buff_raw[0] = LC_1;
  LC_1_buff_filt[0] = LC_1_f;

  LC_2_buff_raw[0] = LC_2;
  LC_2_buff_filt[0] = LC_2_f;

  LC_3_buff_raw[0] = LC_3;
  LC_3_buff_filt[0] = LC_3_f;

  LC_4_buff_raw[0] = LC_4;
  LC_4_buff_filt[0] = LC_4_f;

}

//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

///// setupADC function /////

void setupADC()
{
  //Set up ADC pin modes
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

//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

///// Read ADC Channel Function /////

int16_t readADChannel(byte ch_number)
{
  uint8_t ch;
  int16_t rawdata;
  byte ctrl;
  uint16_t indata;

  //pull down /TFS to write the data
  digitalWrite(TFS, LOW);
  ch_number -= 1;
  ctrl = 0x00; //set control register
  for (int i = 0; i < 3; i++)
  {
    bitWrite(ctrl, i + 2, bitRead(ch_number, i));
  }

  for (int i = 0; i < 5; i++)
  {
    digitalWrite(SCLK, HIGH);
    digitalWrite(DATAOUT, bitRead(ctrl, 4 - i));
    delayMicroseconds(SCLK_DELAY);
    digitalWrite(SCLK, LOW); // on the falling edge the data bit is actually written to ADC
    delayMicroseconds(SCLK_DELAY);
  }
  // provide the 6th falling edge as per specsheet
  digitalWrite(SCLK, HIGH);
  delayMicroseconds(SCLK_DELAY);
  digitalWrite(SCLK, LOW);
  delayMicroseconds(SCLK_DELAY);
  digitalWrite(TFS, HIGH);// restore TFS signal

  // start conversion
  delayMicroseconds(RW_DELAY);
  digitalWrite(CONVST, HIGH);  // initiate conversion
  delayMicroseconds(CONVST_DELAY); // conversion ends 5.9 us later
  digitalWrite(CONVST, LOW);  // restore start conversion signal

  // pull down /RFS to read the data
  digitalWrite(RFS, LOW); // since SCLK is low now, the next rising edge will clock the data
  delayMicroseconds(SCLK_DELAY);
  indata = 0x0000;
  for (int i = 0; i < 16; i++)
  {
    digitalWrite(SCLK, HIGH); // data bit is clocked 35ns after this rising edge
    delayMicroseconds(SCLK_DELAY);
    digitalWrite(SCLK, LOW);
    bitWrite(indata, 15 - i, digitalRead(DATAIN)); // read the data right after the falling edge
    delayMicroseconds(SCLK_DELAY);
  }
  digitalWrite(RFS, HIGH); // restore the RFS signal and put ADC in tristate [20ns min after last falling edge]

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
