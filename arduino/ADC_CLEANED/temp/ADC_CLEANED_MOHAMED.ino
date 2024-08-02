///// TORQUE TRANSDUCER AND EASYCA-3/23/2023//////// 

#define CUSTOM 
#include "TeensySlaveMB2.h" 
#include "EasyCat.h"
#include <SPI.h>
#include <Encoder.h>

//-------- ADC AN7890BNZ-10 -------//
//ADC channels 

const byte  CH_NUM_LC_1 = 1;   
const byte  CH_NUM_LC_2 = 2;   // comment out if not needed      

// Define ADC Pins

const uint16_t  CONVST  = 38;
const uint16_t  SCLK    = 37; 
const uint16_t  TFS     = 36; 
const uint16_t  RFS     = 35; 
const uint16_t  DATAIN  = 34; 
const uint16_t  DATAOUT = 33; 

// CLOCK AT 72 MHZ ////////

const uint16_t  CONVST_DELAY  = 6 ;  

// Timers intervals 
const uint16_t ADC_TIMER_INTERVAL    =  200 ;       //[.us]
const uint16_t FILTER_TIMER_INTERVAL =  1000;      //[kHz]

// Variables 
const uint16_t  PNTS_TO_AVG = 5;                // Average points to read 

// CLOCK AT 72 MHZ ////////

const double    SCLK_DELAY= 0.25;                           
const double    RW_DELAY  = 0.5; 
//Analog signals (ADC) 

volatile unsigned long ADC_cycles = 0; 
        
// Analog signals (ADC) 
double              LC_1_raw = 0.0; 
double              LC_2_raw = 0.0;
double              E4T_reading = 0.0;
double              LC_1_local = 0.0;
double              LC_2_local = 0.0;   // comment out if there is no a second input
volatile double     LC_1_f     = 0.0;
volatile double     LC_2_f     = 0.0;   // comment out if there is no a second input
volatile double     LC_1       = 0.0; 
volatile double     LC_2       = 0.0;   // comment out if there is no a second input
volatile long       sum_LC_1   = 0;
volatile long       sum_LC_2   = 0;     // comment out if there is no a second input

/////////////////////// Filter - properties: Butterworth, 2nd order, 12 HZ passband--Implemented by Lorenzo 
// Update filter coefs 
const double a_lc[] = {1.0,  -1.911197067426073, 0.914975834801433};
const double b_lc[] = {0.0009446918438401619,   0.001889383687680, 0.0009446918438401619};

volatile double LC_1_buff_raw[]  = {0.0,0.0,0.0,0.0};
volatile double LC_2_buff_raw[]  = {0.0,0.0,0.0,0.0};
volatile double LC_1_buff_filt[] = {0.0,0.0,0.0,0.0};
volatile double LC_2_buff_filt[] = {0.0,0.0,0.0,0.0};

int16_t rawDataADC =0;
int16_t ADC_data = 0;

unsigned  long t1= 0;
unsigned  long t = 0;
unsigned  long t0= 0;
unsigned  long delta_t = 0;

Encoder E4T(15,16);

/////// EasyCAT ////// 
EasyCAT  EASYCAT(10);

// Timers instances 
IntervalTimer ADCTimer;
IntervalTimer FilterTimer;

void setup() {
  Serial.begin(9600);
  setupADC();
  ADCTimer.begin(functionADCTimer, ADC_TIMER_INTERVAL);
  FilterTimer.begin(functionFilterTimer, FILTER_TIMER_INTERVAL);
  Serial.print ("\nEasyCAT - Generic EtherCAT slave\n");          // print the banner

  pinMode(13, OUTPUT);                                            // Indicator LED
  E4T.write(0);
  
                                                             //---- initialize the EasyCAT board -----                                                              
  if (EASYCAT.Init() == true)                                     // initialization
  {                                                               // succesfully completed
    Serial.print ("initialized");                                 //
  }                                                               //
  
  else                                                            // initialization failed   
  {                                                               // the EasyCAT board was not recognized
    Serial.print ("initialization failed");                       //     
                                                             
    pinMode(13, OUTPUT);                                          // stay in loop for ever                                                    
  }
}

void loop() {
 
  t = millis();
  t1 = micros();
  delta_t = t - t0;
 
  noInterrupts();
  LC_1_local = LC_1_f; //LC_1_raw ;
  LC_2_local = LC_2_f ;//LC_2_f;

  E4T_reading = E4T.read() / 4000.0 * 360.0;
    
  interrupts();

   
//EASYCAT.MainTask();

if (delta_t >= 1)
 {
    t0 = t;

  //Serial.print(t);
 // Serial.print(", ");
Serial.print( LC_1_local);
Serial.print(", ");
Serial.println(LC_2_local);


//Application();       // Turn on for EasyCAT 
 
 }
}

void Application ()                                        
{
 
  EASYCAT.BufferIn.Cust.Force1 = LC_2_local ; 
 // EASYCAT.BufferIn.Cust.Force2 = LC_2_local ;
  EASYCAT.BufferIn.Cust.Force2 = E4T_reading;
  }

void functionADCTimer()
{

  sum_LC_1 += (long ) (readADChannel(CH_NUM_LC_1));
  sum_LC_2 += (long ) (readADChannel(CH_NUM_LC_2));

  ADC_cycles++;
  
  if (ADC_cycles == PNTS_TO_AVG)
  {
     LC_1_raw = ((double) (sum_LC_1)) / PNTS_TO_AVG;
     LC_2_raw = ((double) (sum_LC_2)) / PNTS_TO_AVG;
      
    ///// Load cell calibration 3.0 convert LC readings to Newton /////
    LC_1 = 1 * LC_1_raw + 0.0;
    LC_2 = 1 * LC_2_raw + 0.0;
 
    ADC_cycles = 0;
 
    sum_LC_1 = 0;
    sum_LC_2 = 0;
  }
}


void functionFilterTimer()
{

  ////// FILTER /////
  int i=0;
  // compute filtered outputs

  noInterrupts();
  LC_1_f = b_lc[0] * LC_1;
  LC_2_f = b_lc[0] * LC_2;

  interrupts();
  
  for (i = 1; i < 3; i++)
  {
    LC_1_f += b_lc[i] * LC_1_buff_raw[i - 1] - a_lc[i] * LC_1_buff_filt[i - 1];
    LC_2_f += b_lc[i] * LC_2_buff_raw[i - 1] - a_lc[i] * LC_2_buff_filt[i - 1];
  }
  // Serial.println(LC_1_f);
 //  Serial.println(LC_2_f);
 
  // update buffers
  for (i = 3; i > 0; i--)
  {
    LC_1_buff_raw[i]  = LC_1_buff_raw[i - 1];
    LC_1_buff_filt[i] = LC_1_buff_filt[i - 1];
    LC_2_buff_filt[i] = LC_2_buff_filt[i - 1];
    LC_2_buff_filt[i] = LC_2_buff_filt[i - 1];
    //

  }
  LC_1_buff_raw[0]  =  LC_1;
  LC_1_buff_filt[0] =  LC_1_f;
  LC_2_buff_raw[0] = LC_2;
  LC_2_buff_filt[0] = LC_2_f;
  //

}

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

///// Read ADC ///// 
int16_t readADChannel(byte ch_number)
{
  byte ctrl;
  uint8_t ch;
  uint16_t indata;
  int16_t  rawdata;

  digitalWrite(TFS, LOW); //pull down /TFS to write the data
  
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

