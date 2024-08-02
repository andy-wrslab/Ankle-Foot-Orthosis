/*
 * MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_private.h
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

#ifndef RTW_HEADER_MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_private_h_
#define RTW_HEADER_MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_private_h_
#include "rtwtypes.h"
#include "multiword_types.h"
#include "zero_crossing_types.h"
#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo.h"
#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_types.h"

/* Private macros used by the generated code to access rtModel */
#ifndef rtmIsMajorTimeStep
#define rtmIsMajorTimeStep(rtm)        (((rtm)->Timing.simTimeStep) == MAJOR_TIME_STEP)
#endif

#ifndef rtmIsMinorTimeStep
#define rtmIsMinorTimeStep(rtm)        (((rtm)->Timing.simTimeStep) == MINOR_TIME_STEP)
#endif

#ifndef rtmSetTPtr
#define rtmSetTPtr(rtm, val)           ((rtm)->Timing.t = (val))
#endif

extern unsigned int xmlecatArr_0_count;
extern unsigned char xmlecatArr_0[];
extern int_T slrtEcatDCM[8];           // From master shift controller
namespace slrealtime
{
  namespace tracing
  {
    struct IamRoot;
  }
}

extern void* slrtRegisterSignalToLoggingService(uintptr_t sigAddr);
extern void MotorTorqueC_MATLABFunction(real_T rtu_sig_in, const real_T
  rtu_prev_buf[200], real_T rtu_N, real_T rtu_prev_updated_idx,
  B_MATLABFunction_MotorTorqueC_T *localB);
extern void MotorTor_TriggeredSubsystem(real_T rtu_Trigger, real_T rtu_offset,
  B_TriggeredSubsystem_MotorTor_T *localB, DW_TriggeredSubsystem_MotorTo_T
  *localDW, ZCE_TriggeredSubsystem_MotorT_T *localZCE);

#endif
/* RTW_HEADER_MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_private_h_ */
