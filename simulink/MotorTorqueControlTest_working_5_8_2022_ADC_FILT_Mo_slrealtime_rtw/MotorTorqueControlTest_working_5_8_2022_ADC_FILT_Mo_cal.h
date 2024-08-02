#ifndef RTW_HEADER_MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_cal_h_
#define RTW_HEADER_MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_cal_h_
#include "rtwtypes.h"

/* Storage class 'PageSwitching', for system '<Root>' */
struct MotorTorqueControlTest_cal_type {
  real_T Memory_InitialCondition[200]; /* Expression: zeros(200,1)
                                        * Referenced by: '<S8>/Memory'
                                        */
  real_T Memory2_InitialCondition[200];/* Expression: zeros(200,1)
                                        * Referenced by: '<S8>/Memory2'
                                        */
  real_T undorder12Hz2_NumCoef[3];   /* Expression: [0.0013    0.0027    0.0013]
                                      * Referenced by: '<S7>/2nd order, 12Hz2'
                                      */
  real_T undorder12Hz2_DenCoef[3];   /* Expression: [1.0000   -1.8935    0.8989]
                                      * Referenced by: '<S7>/2nd order, 12Hz2'
                                      */
  real_T undorder60Hz_NumCoef[3];
  /* Expression: [0.027859766117136         0.055719532234272         0.027859766117136]
   * Referenced by: '<S7>/2nd order, 60Hz'
   */
  real_T undorder60Hz_DenCoef[3];
          /* Expression: [1         -1.47548044359265          0.58691950806119]
           * Referenced by: '<S7>/2nd order, 60Hz'
           */
  real_T DiscretePIDController_InitialCo;
                              /* Mask Parameter: DiscretePIDController_InitialCo
                               * Referenced by: '<S42>/Integrator'
                               */
  real_T PIDController_InitialConditionF;
                              /* Mask Parameter: PIDController_InitialConditionF
                               * Referenced by: '<S90>/Integrator'
                               */
  real_T PIDController_LowerSaturationLi;
                              /* Mask Parameter: PIDController_LowerSaturationLi
                               * Referenced by: '<S97>/Saturation'
                               */
  real_T PIDController_UpperSaturationLi;
                              /* Mask Parameter: PIDController_UpperSaturationLi
                               * Referenced by: '<S97>/Saturation'
                               */
  real_T Gain5_Gain;                   /* Expression: 1000
                                        * Referenced by: '<S6>/Gain5'
                                        */
  real_T Zero_Value;                   /* Expression: 0
                                        * Referenced by: '<S6>/Zero'
                                        */
  real_T Constant38_Value;             /* Expression: 0
                                        * Referenced by: '<Root>/Constant38'
                                        */
  real_T Constant33_Value;             /* Expression: 1
                                        * Referenced by: '<Root>/Constant33'
                                        */
  real_T Constant32_Value;             /* Expression: 0
                                        * Referenced by: '<Root>/Constant32'
                                        */
  real_T Constant31_Value;             /* Expression: 1
                                        * Referenced by: '<Root>/Constant31'
                                        */
  real_T Constant1_Value;              /* Expression: 0
                                        * Referenced by: '<Root>/Constant1'
                                        */
  real_T Constant30_Value;             /* Expression: 999
                                        * Referenced by: '<Root>/Constant30'
                                        */
  real_T Memory1_InitialCondition;     /* Expression: 0
                                        * Referenced by: '<S8>/Memory1'
                                        */
  real_T Memory3_InitialCondition;     /* Expression: 0
                                        * Referenced by: '<S8>/Memory3'
                                        */
  real_T RateTransition_InitialCondition;/* Expression: 0
                                          * Referenced by: '<S8>/Rate Transition'
                                          */
  real_T RateTransition1_InitialConditio;/* Expression: 0
                                          * Referenced by: '<S8>/Rate Transition1'
                                          */
  real_T TmpRTBAtTriggeredSubsystemInpor;/* Expression: 0
                                          * Referenced by:
                                          */
  real_T TmpRTBAtTriggeredSubsystem1Inpo;/* Expression: 0
                                          * Referenced by:
                                          */
  real_T TmpRTBAtMATLABFunction1Inport2_;/* Expression: 0
                                          * Referenced by:
                                          */
  real_T TmpRTBAtMATLABFunction1Inport4_;/* Expression: 0
                                          * Referenced by:
                                          */
  real_T TmpRTBAtMATLABFunction1Outport2;/* Expression: 0
                                          * Referenced by:
                                          */
  real_T TmpRTBAtMATLABFunctionInport2_I;/* Expression: 0
                                          * Referenced by:
                                          */
  real_T TmpRTBAtMATLABFunctionInport4_I;/* Expression: 0
                                          * Referenced by:
                                          */
  real_T TmpRTBAtMATLABFunctionOutport2_;/* Expression: 0
                                          * Referenced by:
                                          */
  real_T TmpRTBAtMemory2Inport1_InitialC;/* Expression: 0
                                          * Referenced by:
                                          */
  real_T newbuf_InitialCondition;      /* Expression: 0
                                        * Referenced by:
                                        */
  real_T Constant_Value;               /* Expression: 200
                                        * Referenced by: '<S8>/Constant'
                                        */
  real_T Constant1_Value_a;            /* Expression: 200
                                        * Referenced by: '<S8>/Constant1'
                                        */
  real_T Gain_Gain;                    /* Expression: 1/200
                                        * Referenced by: '<S8>/Gain'
                                        */
  real_T Gain1_Gain;                   /* Expression: 1/200
                                        * Referenced by: '<S8>/Gain1'
                                        */
  real_T Gain1_Gain_i;                 /* Expression: 360/8192
                                        * Referenced by: '<Root>/Gain1'
                                        */
  real_T Memory_InitialCondition_l;    /* Expression: 0
                                        * Referenced by: '<Root>/Memory'
                                        */
  real_T SpringconstantNmdeg_Value;    /* Expression: 0.7651
                                        * Referenced by: '<Root>/Spring constant Nm//deg'
                                        */
  real_T Zero1_Value;                  /* Expression: 0
                                        * Referenced by: '<S6>/Zero1'
                                        */
  real_T Gain_Gain_j;                  /* Expression: -1000
                                        * Referenced by: '<S6>/Gain'
                                        */
  real_T Nmdeg_Value;                  /* Expression: 0.5
                                        * Referenced by: '<Root>/Nm // deg'
                                        */
  real_T FeedbackP2_Gain;              /* Expression: 1000
                                        * Referenced by: '<S6>/-FeedbackP2'
                                        */
  real_T Constant34_Value;             /* Expression: -30
                                        * Referenced by: '<Root>/Constant34'
                                        */
  real_T Constant35_Value;             /* Expression: 28
                                        * Referenced by: '<Root>/Constant35'
                                        */
  real_T Constant36_Value;             /* Expression: -0.1
                                        * Referenced by: '<Root>/Constant36'
                                        */
  real_T FeedbackP1_Gain;              /* Expression: 1000
                                        * Referenced by: '<S6>/-FeedbackP1'
                                        */
  real_T DeadZone1_Start;              /* Expression: -70
                                        * Referenced by: '<S6>/Dead Zone1'
                                        */
  real_T DeadZone1_End;                /* Expression: 70
                                        * Referenced by: '<S6>/Dead Zone1'
                                        */
  real_T P1_Value;                     /* Expression: 0.7
                                        * Referenced by: '<Root>/P1'
                                        */
  real_T Integrator_gainval;           /* Computed Parameter: Integrator_gainval
                                        * Referenced by: '<S42>/Integrator'
                                        */
  real_T I1_Value;                     /* Expression: 0.4
                                        * Referenced by: '<Root>/I1'
                                        */
  real_T DeadZone_Start;               /* Expression: 0
                                        * Referenced by: '<S6>/Dead Zone'
                                        */
  real_T DeadZone_End;                 /* Expression: 0
                                        * Referenced by: '<S6>/Dead Zone'
                                        */
  real_T Integrator_gainval_f;       /* Computed Parameter: Integrator_gainval_f
                                      * Referenced by: '<S90>/Integrator'
                                      */
  real_T SineWaveFunction_Amp;         /* Expression: 24
                                        * Referenced by: '<Root>/Sine Wave Function'
                                        */
  real_T SineWaveFunction_Bias;        /* Expression: 0
                                        * Referenced by: '<Root>/Sine Wave Function'
                                        */
  real_T SineWaveFunction_Freq;        /* Expression: 0.5 * 6.28
                                        * Referenced by: '<Root>/Sine Wave Function'
                                        */
  real_T SineWaveFunction_Phase;       /* Expression: 0
                                        * Referenced by: '<Root>/Sine Wave Function'
                                        */
  real_T Gain_Gain_b;                  /* Expression: 1
                                        * Referenced by: '<Root>/Gain'
                                        */
  real_T Constant2_Value;              /* Expression: 9
                                        * Referenced by: '<S1>/Constant2'
                                        */
  real_T undorder12Hz2_InitialStates;  /* Expression: 0
                                        * Referenced by: '<S7>/2nd order, 12Hz2'
                                        */
  real_T undorder60Hz_InitialStates;   /* Expression: 0
                                        * Referenced by: '<S7>/2nd order, 60Hz'
                                        */
  real_T Switch4_Threshold;            /* Expression: 0
                                        * Referenced by: '<Root>/Switch4'
                                        */
  real_T TmpRTBAtMotorInitliazation1Inpo;/* Expression: 0
                                          * Referenced by:
                                          */
  real_T Memory8_InitialCondition;     /* Expression: 1024
                                        * Referenced by: '<Root>/Memory8'
                                        */
  real_T Memory9_InitialCondition;     /* Expression: 0
                                        * Referenced by: '<Root>/Memory9'
                                        */
  uint16_T TmpRTBAtEtherCATPDOTransmitInpo;
                          /* Computed Parameter: TmpRTBAtEtherCATPDOTransmitInpo
                           * Referenced by:
                           */
  uint8_T ManualSwitch11_CurrentSetting;
                            /* Computed Parameter: ManualSwitch11_CurrentSetting
                             * Referenced by: '<Root>/Manual Switch11'
                             */
  uint8_T ManualSwitch1_CurrentSetting;
                             /* Computed Parameter: ManualSwitch1_CurrentSetting
                              * Referenced by: '<Root>/Manual Switch1'
                              */
  uint8_T ManualSwitch10_CurrentSetting;
                            /* Computed Parameter: ManualSwitch10_CurrentSetting
                             * Referenced by: '<S6>/Manual Switch10'
                             */
  uint8_T ManualSwitch10_CurrentSetting_h;
                          /* Computed Parameter: ManualSwitch10_CurrentSetting_h
                           * Referenced by: '<Root>/Manual Switch10'
                           */
};

/* Storage class 'PageSwitching' */
extern MotorTorqueControlTest_cal_type MotorTorqueControlTest_cal_impl;
extern MotorTorqueControlTest_cal_type *MotorTorqueControlTest_work_cal;

#endif
     /* RTW_HEADER_MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_cal_h_ */
