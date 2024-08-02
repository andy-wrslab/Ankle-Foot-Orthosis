/*
 *  rtmodel.cpp:
 *
 * Academic License - for use in teaching, academic research, and meeting
 * course requirements at degree granting institutions only.  Not for
 * government, commercial, or other organizational use.
 *
 * Code generation for model "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo".
 *
 * Model version              : 3.98
 * Simulink Coder version : 9.8 (R2022b) 13-May-2022
 * C++ source code generated on : Mon Jul  1 21:27:12 2024
 *
 * Target selection: slrealtime.tlc
 * Note: GRT includes extra infrastructure and instrumentation for prototyping
 * Embedded hardware selection: Intel->x86-64 (Linux 64)
 * Code generation objectives: Unspecified
 * Validation result: Not run
 */

#include "rtmodel.h"

/* Use this function only if you need to maintain compatibility with an existing static main program. */
void MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step(int_T tid)
{
  switch (tid) {
   case 0 :
    MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step0();
    break;

   case 1 :
    MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step2();
    break;

   case 2 :
    MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step3();
    break;

   default :
    /* do nothing */
    break;
  }
}
