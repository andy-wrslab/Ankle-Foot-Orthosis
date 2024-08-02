/*
 * MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo.h
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

#ifndef RTW_HEADER_MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_h_
#define RTW_HEADER_MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_h_
#include <logsrv.h>
#include "rtwtypes.h"
#include "rtw_extmode.h"
#include "rtw_continuous.h"
#include "rtw_solver.h"
#include "verify/verifyIntrf.h"
#include "stddef.h"
#include "stdlib.h"
#include "string"
#include "Logger.hpp"
#include "slecatutils.h"
#include "sl_types_def.h"
#include "StartCallbackAPI.h"
#include "sysran_types.h"
#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_types.h"

extern "C"
{

#include "rtGetNaN.h"

}

extern "C"
{

#include "rt_nonfinite.h"

}

#include "rt_zcfcn.h"
#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_cal.h"

extern "C"
{

#include "rtGetInf.h"

}

#include <cstring>
#include "zero_crossing_types.h"

/* Macros for accessing real-time model data structure */
#ifndef rtmCounterLimit
#define rtmCounterLimit(rtm, idx)      ((rtm)->Timing.TaskCounters.cLimit[(idx)])
#endif

#ifndef rtmGetErrorStatus
#define rtmGetErrorStatus(rtm)         ((rtm)->errorStatus)
#endif

#ifndef rtmSetErrorStatus
#define rtmSetErrorStatus(rtm, val)    ((rtm)->errorStatus = (val))
#endif

#ifndef rtmStepTask
#define rtmStepTask(rtm, idx)          ((rtm)->Timing.TaskCounters.TID[(idx)] == 0)
#endif

#ifndef rtmGetStopRequested
#define rtmGetStopRequested(rtm)       ((rtm)->Timing.stopRequestedFlag)
#endif

#ifndef rtmSetStopRequested
#define rtmSetStopRequested(rtm, val)  ((rtm)->Timing.stopRequestedFlag = (val))
#endif

#ifndef rtmGetStopRequestedPtr
#define rtmGetStopRequestedPtr(rtm)    (&((rtm)->Timing.stopRequestedFlag))
#endif

#ifndef rtmGetT
#define rtmGetT(rtm)                   (rtmGetTPtr((rtm))[0])
#endif

#ifndef rtmGetTPtr
#define rtmGetTPtr(rtm)                ((rtm)->Timing.t)
#endif

#ifndef rtmTaskCounter
#define rtmTaskCounter(rtm, idx)       ((rtm)->Timing.TaskCounters.TID[(idx)])
#endif

#define MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_M (MotorTorqueControlTest_worki_M)

/* Block signals for system '<S8>/MATLAB Function' */
struct B_MATLABFunction_MotorTorqueC_T {
  real_T newbuf[200];                  /* '<S8>/MATLAB Function' */
  real_T last_updated_idx;             /* '<S8>/MATLAB Function' */
};

/* Block signals for system '<S8>/Triggered Subsystem' */
struct B_TriggeredSubsystem_MotorTor_T {
  real_T offset;                       /* '<S109>/offset' */
};

/* Block states (default storage) for system '<S8>/Triggered Subsystem' */
struct DW_TriggeredSubsystem_MotorTo_T {
  int8_T TriggeredSubsystem_SubsysRanBC;/* '<S8>/Triggered Subsystem' */
};

/* Zero-crossing (trigger) state for system '<S8>/Triggered Subsystem' */
struct ZCE_TriggeredSubsystem_MotorT_T {
  ZCSigState TriggeredSubsystem_Trig_ZCE;/* '<S8>/Triggered Subsystem' */
};

/* Block signals (default storage) */
struct B_MotorTorqueControlTest_work_T {
  real_T Gain1;                        /* '<Root>/Gain1' */
  real_T ManualSwitch11;               /* '<Root>/Manual Switch11' */
  real_T Memory;                       /* '<Root>/Memory' */
  real_T ActualTorque;                 /* '<Root>/Product' */
  real_T DesiredVelocity_mRPM;         /* '<S6>/Gain' */
  real_T Product1;                     /* '<Root>/Product1' */
  real_T ManualSwitch1;                /* '<Root>/Manual Switch1' */
  real_T Feedback_signal_torque;       /* '<S6>/-FeedbackP2' */
  real_T BumperTorque;                 /* '<S6>/Manual Switch10' */
  real_T FeedbackP1;                   /* '<S6>/-FeedbackP1' */
  real_T torque_error;                 /* '<S6>/Sum' */
  real_T DeadZone1;                    /* '<S6>/Dead Zone1' */
  real_T PProdOut;                     /* '<S47>/PProd Out' */
  real_T Integrator;                   /* '<S42>/Integrator' */
  real_T Sum;                          /* '<S51>/Sum' */
  real_T IProdOut;                     /* '<S39>/IProd Out' */
  real_T DeadZone;                     /* '<S6>/Dead Zone' */
  real_T PProdOut_k;                   /* '<S95>/PProd Out' */
  real_T Integrator_j;                 /* '<S90>/Integrator' */
  real_T Sum_o;                        /* '<S99>/Sum' */
  real_T Saturation;                   /* '<S97>/Saturation' */
  real_T IProdOut_l;                   /* '<S87>/IProd Out' */
  real_T SineWaveFunction;             /* '<Root>/Sine Wave Function' */
  real_T AssistiveTorque;              /* '<Root>/Gain' */
  real_T ManualSwitch10;               /* '<Root>/Manual Switch10' */
  real_T Filtered;                     /* '<S7>/2nd order, 12Hz2' */
  real_T u_60Hz;                       /* '<S7>/2nd order, 60Hz' */
  real_T Switch4;                      /* '<Root>/Switch4' */
  real_T TmpRTBAtMotorInitliazation1Inpo;/* '<Root>/Switch4' */
  real_T PressureInsoleRaw;            /* '<Root>/RT' */
  real_T Memory8;                      /* '<Root>/Memory8' */
  real_T Memory9;                      /* '<Root>/Memory9' */
  real_T Memory_i[200];                /* '<S8>/Memory' */
  real_T Memory1;                      /* '<S8>/Memory1' */
  real_T Memory2[200];                 /* '<S8>/Memory2' */
  real_T Memory3;                      /* '<S8>/Memory3' */
  real_T TmpRTBAtTriggeredSubsystemInpor;/* '<S8>/Gain' */
  real_T Sum_p;                        /* '<S8>/Sum' */
  real_T TmpRTBAtTriggeredSubsystem1Inpo;/* '<S8>/Gain1' */
  real_T Sum1;                         /* '<S8>/Sum1' */
  real_T TmpRTBAtMATLABFunction1Outport2;/* '<S8>/MATLAB Function1' */
  real_T TmpRTBAtMATLABFunctionOutport2;/* '<S8>/MATLAB Function' */
  real_T buffer[200];                  /* '<S8>/MATLAB Function1' */
  real_T buffer_e[200];                /* '<S8>/MATLAB Function' */
  real_T RateTransition;               /* '<S8>/Rate Transition' */
  real_T TmpRTBAtMATLABFunctionInport2[200];/* '<S8>/Memory' */
  real_T TmpRTBAtMATLABFunctionInport4;/* '<S8>/Memory1' */
  real_T SumofElements;                /* '<S8>/Sum of Elements' */
  real_T Gain;                         /* '<S8>/Gain' */
  real_T RateTransition1;              /* '<S8>/Rate Transition1' */
  real_T TmpRTBAtMATLABFunction1Inport2[200];/* '<S8>/Memory2' */
  real_T TmpRTBAtMATLABFunction1Inport4;/* '<S8>/Memory3' */
  real_T SumofElements1;               /* '<S8>/Sum of Elements1' */
  real_T Gain1_a;                      /* '<S8>/Gain1' */
  real_T Gain5;                        /* '<S6>/Gain5' */
  real_T Motor_controlword;            /* '<Root>/Motor Initliazation1' */
  real_T pressure_min;                 /* '<Root>/MATLAB Function4' */
  real_T pressure_max;                 /* '<Root>/MATLAB Function4' */
  real_T tau;                          /* '<Root>/MATLAB Function3' */
  real_T y;                            /* '<Root>/MATLAB Function' */
  int32_T EtherCATPDOReceiveCurrentValuef;
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive3' */
  int32_T ActualVelocity;              /* '<S7>/Data Type Conversion2' */
  int32_T EtherCATInit[6];             /* '<S1>/EtherCAT Init' */
  int32_T DataTypeConversion1;         /* '<S6>/Data Type Conversion1' */
  int32_T EtherCATGetState;            /* '<S1>/EtherCAT Get State' */
  int32_T EtherCATPDOReceiveCurrentValu_p;
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive4' */
  int32_T DemandVelocity;              /* '<S7>/Data Type Conversion7' */
  int32_T EtherCATPDOReceiveCurrentValu_c;
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive5' */
  int32_T DemandPosition;              /* '<S7>/Data Type Conversion6' */
  uint16_T EtherCATPDOReceive;         /* '<S1>/EtherCAT PDO Receive' */
  uint16_T TmpRTBAtEtherCATPDOTransmitInpo;/* '<S1>/Data Type Conversion' */
  uint16_T DataTypeConversion1_b;      /* '<S1>/Data Type Conversion1' */
  uint16_T EtherCATPDOReceiveCurrentValu_d;
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive6' */
  uint16_T EtherCATPDOReceiveCurrentValu_n;
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive7' */
  uint16_T ModesofOperation;           /* '<S7>/Data Type Conversion9' */
  uint16_T DataTypeConversion;         /* '<S1>/Data Type Conversion' */
  int16_T EtherCATPDOReceiveCurrentVal_ns;
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive2' */
  int16_T ActualCurrent;               /* '<S7>/Data Type Conversion5' */
  int16_T DemandCurrent;               /* '<S7>/Data Type Conversion8' */
  B_TriggeredSubsystem_MotorTor_T TriggeredSubsystem1;/* '<S8>/Triggered Subsystem1' */
  B_TriggeredSubsystem_MotorTor_T TriggeredSubsystem;/* '<S8>/Triggered Subsystem' */
  B_MATLABFunction_MotorTorqueC_T sf_MATLABFunction1;/* '<S8>/MATLAB Function1' */
  B_MATLABFunction_MotorTorqueC_T sf_MATLABFunction_l;/* '<S8>/MATLAB Function' */
};

/* Block states (default storage) for system '<Root>' */
struct DW_MotorTorqueControlTest_wor_T {
  real_T Integrator_DSTATE;            /* '<S42>/Integrator' */
  real_T Integrator_DSTATE_l;          /* '<S90>/Integrator' */
  real_T undorder12Hz2_states[2];      /* '<S7>/2nd order, 12Hz2' */
  real_T undorder60Hz_states[2];       /* '<S7>/2nd order, 60Hz' */
  real_T Memory_PreviousInput;         /* '<Root>/Memory' */
  real_T undorder12Hz2_tmp;            /* '<S7>/2nd order, 12Hz2' */
  real_T undorder60Hz_tmp;             /* '<S7>/2nd order, 60Hz' */
  real_T TmpRTBAtMotorInitliazation1Inpo;/* synthesized block */
  real_T TmpRTBAtMotorInitliazation1In_f;/* synthesized block */
  real_T TmpRTBAtMotorInitliazation1In_e;/* synthesized block */
  real_T Memory8_PreviousInput;        /* '<Root>/Memory8' */
  real_T Memory9_PreviousInput;        /* '<Root>/Memory9' */
  real_T Memory_PreviousInput_b[200];  /* '<S8>/Memory' */
  real_T Memory1_PreviousInput;        /* '<S8>/Memory1' */
  real_T Memory2_PreviousInput[200];   /* '<S8>/Memory2' */
  real_T Memory3_PreviousInput;        /* '<S8>/Memory3' */
  real_T RateTransition_Buf[2];        /* '<S8>/Rate Transition' */
  real_T RateTransition1_Buf[2];       /* '<S8>/Rate Transition1' */
  real_T TmpRTBAtTriggeredSubsystemInpor[3];/* synthesized block */
  real_T TmpRTBAtTriggeredSubsystem1Inpo[3];/* synthesized block */
  real_T TmpRTBAtMATLABFunction1Inport2_[200];/* synthesized block */
  real_T TmpRTBAtMATLABFunction1Inport_p[200];/* synthesized block */
  real_T TmpRTBAtMATLABFunction1Inport_a[200];/* synthesized block */
  real_T TmpRTBAtMATLABFunction1Inport4_;/* synthesized block */
  real_T TmpRTBAtMATLABFunction1Inport_h;/* synthesized block */
  real_T TmpRTBAtMATLABFunction1Inport_j;/* synthesized block */
  real_T TmpRTBAtMATLABFunction1Outport2[3];/* synthesized block */
  real_T TmpRTBAtMATLABFunctionInport2_B[200];/* synthesized block */
  real_T TmpRTBAtMATLABFunctionInport2_c[200];/* synthesized block */
  real_T TmpRTBAtMATLABFunctionInport2_f[200];/* synthesized block */
  real_T TmpRTBAtMATLABFunctionInport4_B;/* synthesized block */
  real_T TmpRTBAtMATLABFunctionInport4_g;/* synthesized block */
  real_T TmpRTBAtMATLABFunctionInport4_d;/* synthesized block */
  real_T TmpRTBAtMATLABFunctionOutport2_[3];/* synthesized block */
  real_T TmpRTBAtMemory2Inport1_Buf[600];/* synthesized block */
  real_T newbuf_Buf[600];              /* synthesized block */
  struct {
    real_T EXECRATIO;
  } EtherCATInit_RWORK;                /* '<S1>/EtherCAT Init' */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Gain_;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Feedb;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Actua;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_DeadZ;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Discr;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Sum_a;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Dea_h;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_PIDCo;   /* synthesized block */

  struct {
    void *LoggedData[2];
  } Scope_PWORK;                       /* '<Root>/Scope' */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Ether;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_From3;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_From4;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Gai_a;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_MATLA;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_MAT_h;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Produ;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Senso;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Sen_c;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Sen_f;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Se_cy;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Sen_g;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_SineW;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Trigg;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Tri_e;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Eth_k;   /* synthesized block */

  void* TmpRTBAtEtherCATPDOTransmitInpo;/* synthesized block */
  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Eth_l;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_DataT;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Dat_f;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Dat_n;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Dat_i;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Dat_o;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Da_ob;   /* synthesized block */

  void* TmpRTBAtMotorInitliazation1In_b;/* synthesized block */
  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_Motor;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_MAT_n;   /* synthesized block */

  struct {
    void *AQHandles;
  } TAQSigLogging_InsertedFor_MAT_g;   /* synthesized block */

  void* TmpRTBAtTriggeredSubsystemInp_b;/* synthesized block */
  void* TmpRTBAtTriggeredSubsystem1In_j;/* synthesized block */
  void* TmpRTBAtMATLABFunction1Inport_d;/* synthesized block */
  void* TmpRTBAtMATLABFunction1Inport_n;/* synthesized block */
  void* TmpRTBAtMATLABFunction1Outpor_o;/* synthesized block */
  void* TmpRTBAtMATLABFunctionInport2_d;/* synthesized block */
  void* TmpRTBAtMATLABFunctionInport4_m;/* synthesized block */
  void* TmpRTBAtMATLABFunctionOutport_h;/* synthesized block */
  void* TmpRTBAtMemory2Inport1_d0_SEMAP;/* synthesized block */
  void* newbuf_d0_SEMAPHORE;           /* synthesized block */
  int32_T sfEvent;                     /* '<Root>/Motor Initliazation1' */
  uint32_T is_c25_MotorTorqueControlTest_w;/* '<Root>/Motor Initliazation1' */
  int_T EtherCATPDOReceiveCurrentValuef[7];
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive2' */
  int_T EtherCATPDOReceiveCurrentValu_i[7];
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive3' */
  int_T EtherCATPDOReceive_IWORK[7];   /* '<S1>/EtherCAT PDO Receive' */
  int_T EtherCATPDOTransmitTargetTorque[7];
                              /* '<S6>/EtherCAT PDO Transmit - Target Torque' */
  int_T EtherCATPDOTransmit_IWORK[7];  /* '<S1>/EtherCAT PDO Transmit' */
  int_T EtherCATPDOTransmit1_IWORK[7]; /* '<S1>/EtherCAT PDO Transmit1' */
  int_T EtherCATGetState_IWORK;        /* '<S1>/EtherCAT Get State' */
  int_T EtherCATPDOReceiveCurrentValu_m[7];
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive4' */
  int_T EtherCATPDOReceiveCurrentVal_mf[7];
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive5' */
  int_T EtherCATPDOReceiveCurrentVal_mn[7];
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive6' */
  int_T EtherCATPDOReceiveCurrentVal_m2[7];
                   /* '<S7>/EtherCAT PDO Receive - Current Value from drive7' */
  uint16_T TmpRTBAtEtherCATPDOTransmitIn_n[3];/* synthesized block */
  int8_T Integrator_PrevResetState;    /* '<S90>/Integrator' */
  int8_T TmpRTBAtEtherCATPDOTransmitIn_a;/* synthesized block */
  int8_T TmpRTBAtEtherCATPDOTransmitIn_d;/* synthesized block */
  int8_T TmpRTBAtMotorInitliazation1In_g;/* synthesized block */
  int8_T TmpRTBAtMotorInitliazation1In_d;/* synthesized block */
  int8_T RateTransition_RdBufIdx;      /* '<S8>/Rate Transition' */
  int8_T RateTransition_WrBufIdx;      /* '<S8>/Rate Transition' */
  int8_T RateTransition1_RdBufIdx;     /* '<S8>/Rate Transition1' */
  int8_T RateTransition1_WrBufIdx;     /* '<S8>/Rate Transition1' */
  int8_T TmpRTBAtTriggeredSubsystemInp_g;/* synthesized block */
  int8_T TmpRTBAtTriggeredSubsystemIn_bw;/* synthesized block */
  int8_T TmpRTBAtTriggeredSubsystem1In_d;/* synthesized block */
  int8_T TmpRTBAtTriggeredSubsystem1In_e;/* synthesized block */
  int8_T TmpRTBAtMATLABFunction1Inpor_dg;/* synthesized block */
  int8_T TmpRTBAtMATLABFunction1Inpor_ha;/* synthesized block */
  int8_T TmpRTBAtMATLABFunction1Inpor_hu;/* synthesized block */
  int8_T TmpRTBAtMATLABFunction1Inpor_au;/* synthesized block */
  int8_T TmpRTBAtMATLABFunction1Outpor_l;/* synthesized block */
  int8_T TmpRTBAtMATLABFunction1Outpor_b;/* synthesized block */
  int8_T TmpRTBAtMATLABFunctionInport2_L;/* synthesized block */
  int8_T TmpRTBAtMATLABFunctionInport2_R;/* synthesized block */
  int8_T TmpRTBAtMATLABFunctionInport4_L;/* synthesized block */
  int8_T TmpRTBAtMATLABFunctionInport4_R;/* synthesized block */
  int8_T TmpRTBAtMATLABFunctionOutport_g;/* synthesized block */
  int8_T TmpRTBAtMATLABFunctionOutport_l;/* synthesized block */
  int8_T TmpRTBAtMemory2Inport1_LstBufWR;/* synthesized block */
  int8_T TmpRTBAtMemory2Inport1_RDBuf; /* synthesized block */
  int8_T newbuf_LstBufWR;              /* synthesized block */
  int8_T newbuf_RDBuf;                 /* synthesized block */
  uint8_T is_active_c25_MotorTorqueContro;/* '<Root>/Motor Initliazation1' */
  boolean_T doneDoubleBufferReInit;    /* '<Root>/Motor Initliazation1' */
  DW_TriggeredSubsystem_MotorTo_T TriggeredSubsystem1;/* '<S8>/Triggered Subsystem1' */
  DW_TriggeredSubsystem_MotorTo_T TriggeredSubsystem;/* '<S8>/Triggered Subsystem' */
};

/* Zero-crossing (trigger) state */
struct PrevZCX_MotorTorqueControlTes_T {
  ZCE_TriggeredSubsystem_MotorT_T TriggeredSubsystem1;/* '<S8>/Triggered Subsystem1' */
  ZCE_TriggeredSubsystem_MotorT_T TriggeredSubsystem;/* '<S8>/Triggered Subsystem' */
};

/* Real-time Model Data Structure */
struct tag_RTM_MotorTorqueControlTes_T {
  const char_T *errorStatus;
  RTWSolverInfo solverInfo;

  /*
   * Timing:
   * The following substructure contains information regarding
   * the timing information for the model.
   */
  struct {
    uint32_T clockTick0;
    uint32_T clockTickH0;
    time_T stepSize0;
    uint32_T clockTick1;
    uint32_T clockTickH1;
    uint32_T clockTick2;
    uint32_T clockTickH2;
    uint32_T clockTick3;
    uint32_T clockTickH3;
    struct {
      uint8_T TID[4];
      uint8_T cLimit[4];
    } TaskCounters;

    struct {
      uint8_T TID1_2;
    } RateInteraction;

    SimTimeStep simTimeStep;
    boolean_T stopRequestedFlag;
    time_T *t;
    time_T tArray[4];
  } Timing;
};

/* Block signals (default storage) */
#ifdef __cplusplus

extern "C"
{

#endif

  extern struct B_MotorTorqueControlTest_work_T MotorTorqueControlTest_workin_B;

#ifdef __cplusplus

}

#endif

/* Block states (default storage) */
extern struct DW_MotorTorqueControlTest_wor_T MotorTorqueControlTest_worki_DW;

/* Zero-crossing (trigger) state */
extern PrevZCX_MotorTorqueControlTes_T MotorTorqueControlTest__PrevZCX;

#ifdef __cplusplus

extern "C"
{

#endif

  /* Model entry point functions */
  extern void MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_initialize
    (void);
  extern void MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step0(void);
  extern void MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step2(void);
  extern void MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step3(void);
  extern void MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_terminate(void);

#ifdef __cplusplus

}

#endif

/* Real-time Model object */
#ifdef __cplusplus

extern "C"
{

#endif

  extern RT_MODEL_MotorTorqueControlTe_T *const MotorTorqueControlTest_worki_M;

#ifdef __cplusplus

}

#endif

/*-
 * The generated code includes comments that allow you to trace directly
 * back to the appropriate location in the model.  The basic format
 * is <system>/block_name, where system is the system number (uniquely
 * assigned by Simulink) and block_name is the name of the block.
 *
 * Use the MATLAB hilite_system command to trace the generated code back
 * to the model.  For example,
 *
 * hilite_system('<S3>')    - opens system 3
 * hilite_system('<S3>/Kp') - opens and selects block Kp which resides in S3
 *
 * Here is the system hierarchy for this model
 *
 * '<Root>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo'
 * '<S1>'   : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/EtherCAT Initialization Subsystem1'
 * '<S2>'   : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/MATLAB Function'
 * '<S3>'   : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/MATLAB Function3'
 * '<S4>'   : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/MATLAB Function4'
 * '<S5>'   : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/Motor Initliazation1'
 * '<S6>'   : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1'
 * '<S7>'   : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/Sensor Readings'
 * '<S8>'   : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/Triggered Subsystem6'
 * '<S9>'   : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller'
 * '<S10>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller'
 * '<S11>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Anti-windup'
 * '<S12>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/D Gain'
 * '<S13>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Filter'
 * '<S14>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Filter ICs'
 * '<S15>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/I Gain'
 * '<S16>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Ideal P Gain'
 * '<S17>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Ideal P Gain Fdbk'
 * '<S18>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Integrator'
 * '<S19>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Integrator ICs'
 * '<S20>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/N Copy'
 * '<S21>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/N Gain'
 * '<S22>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/P Copy'
 * '<S23>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Parallel P Gain'
 * '<S24>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Reset Signal'
 * '<S25>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Saturation'
 * '<S26>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Saturation Fdbk'
 * '<S27>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Sum'
 * '<S28>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Sum Fdbk'
 * '<S29>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Tracking Mode'
 * '<S30>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Tracking Mode Sum'
 * '<S31>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Tsamp - Integral'
 * '<S32>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Tsamp - Ngain'
 * '<S33>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/postSat Signal'
 * '<S34>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/preSat Signal'
 * '<S35>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Anti-windup/Passthrough'
 * '<S36>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/D Gain/Disabled'
 * '<S37>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Filter/Disabled'
 * '<S38>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Filter ICs/Disabled'
 * '<S39>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/I Gain/External Parameters'
 * '<S40>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Ideal P Gain/Passthrough'
 * '<S41>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Ideal P Gain Fdbk/Disabled'
 * '<S42>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Integrator/Discrete'
 * '<S43>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Integrator ICs/Internal IC'
 * '<S44>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/N Copy/Disabled wSignal Specification'
 * '<S45>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/N Gain/Disabled'
 * '<S46>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/P Copy/Disabled'
 * '<S47>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Parallel P Gain/External Parameters'
 * '<S48>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Reset Signal/Disabled'
 * '<S49>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Saturation/Passthrough'
 * '<S50>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Saturation Fdbk/Disabled'
 * '<S51>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Sum/Sum_PI'
 * '<S52>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Sum Fdbk/Disabled'
 * '<S53>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Tracking Mode/Disabled'
 * '<S54>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Tracking Mode Sum/Passthrough'
 * '<S55>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Tsamp - Integral/Passthrough'
 * '<S56>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/Tsamp - Ngain/Passthrough'
 * '<S57>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/postSat Signal/Forward_Path'
 * '<S58>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/Discrete PID Controller/preSat Signal/Forward_Path'
 * '<S59>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Anti-windup'
 * '<S60>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/D Gain'
 * '<S61>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Filter'
 * '<S62>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Filter ICs'
 * '<S63>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/I Gain'
 * '<S64>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Ideal P Gain'
 * '<S65>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Ideal P Gain Fdbk'
 * '<S66>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Integrator'
 * '<S67>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Integrator ICs'
 * '<S68>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/N Copy'
 * '<S69>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/N Gain'
 * '<S70>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/P Copy'
 * '<S71>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Parallel P Gain'
 * '<S72>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Reset Signal'
 * '<S73>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Saturation'
 * '<S74>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Saturation Fdbk'
 * '<S75>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Sum'
 * '<S76>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Sum Fdbk'
 * '<S77>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Tracking Mode'
 * '<S78>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Tracking Mode Sum'
 * '<S79>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Tsamp - Integral'
 * '<S80>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Tsamp - Ngain'
 * '<S81>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/postSat Signal'
 * '<S82>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/preSat Signal'
 * '<S83>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Anti-windup/Passthrough'
 * '<S84>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/D Gain/Disabled'
 * '<S85>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Filter/Disabled'
 * '<S86>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Filter ICs/Disabled'
 * '<S87>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/I Gain/External Parameters'
 * '<S88>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Ideal P Gain/Passthrough'
 * '<S89>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Ideal P Gain Fdbk/Disabled'
 * '<S90>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Integrator/Discrete'
 * '<S91>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Integrator ICs/Internal IC'
 * '<S92>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/N Copy/Disabled wSignal Specification'
 * '<S93>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/N Gain/Disabled'
 * '<S94>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/P Copy/Disabled'
 * '<S95>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Parallel P Gain/External Parameters'
 * '<S96>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Reset Signal/External Reset'
 * '<S97>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Saturation/Enabled'
 * '<S98>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Saturation Fdbk/Disabled'
 * '<S99>'  : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Sum/Sum_PI'
 * '<S100>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Sum Fdbk/Disabled'
 * '<S101>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Tracking Mode/Disabled'
 * '<S102>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Tracking Mode Sum/Passthrough'
 * '<S103>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Tsamp - Integral/Passthrough'
 * '<S104>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/Tsamp - Ngain/Passthrough'
 * '<S105>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/postSat Signal/Forward_Path'
 * '<S106>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/PI Velocity controller 1/PID Controller/preSat Signal/Forward_Path'
 * '<S107>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/Triggered Subsystem6/MATLAB Function'
 * '<S108>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/Triggered Subsystem6/MATLAB Function1'
 * '<S109>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/Triggered Subsystem6/Triggered Subsystem'
 * '<S110>' : 'MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo/Triggered Subsystem6/Triggered Subsystem1'
 */
#endif   /* RTW_HEADER_MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_h_ */
