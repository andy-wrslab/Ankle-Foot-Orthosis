#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_cal.h"
#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo.h"

/* Storage class 'PageSwitching' */
MotorTorqueControlTest_cal_type MotorTorqueControlTest_cal_impl = {
  /* Expression: zeros(200,1)
   * Referenced by: '<S8>/Memory'
   */
  { 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0 },

  /* Expression: zeros(200,1)
   * Referenced by: '<S8>/Memory2'
   */
  { 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0 },

  /* Expression: [0.0013    0.0027    0.0013]
   * Referenced by: '<S7>/2nd order, 12Hz2'
   */
  { 0.0013, 0.0027, 0.0013 },

  /* Expression: [1.0000   -1.8935    0.8989]
   * Referenced by: '<S7>/2nd order, 12Hz2'
   */
  { 1.0, -1.8935, 0.8989 },

  /* Expression: [0.027859766117136         0.055719532234272         0.027859766117136]
   * Referenced by: '<S7>/2nd order, 60Hz'
   */
  { 0.027859766117136, 0.055719532234272, 0.027859766117136 },

  /* Expression: [1         -1.47548044359265          0.58691950806119]
   * Referenced by: '<S7>/2nd order, 60Hz'
   */
  { 1.0, -1.47548044359265, 0.58691950806119 },

  /* Mask Parameter: DiscretePIDController_InitialCo
   * Referenced by: '<S42>/Integrator'
   */
  0.0,

  /* Mask Parameter: PIDController_InitialConditionF
   * Referenced by: '<S90>/Integrator'
   */
  0.0,

  /* Mask Parameter: PIDController_LowerSaturationLi
   * Referenced by: '<S97>/Saturation'
   */
  -5000.0,

  /* Mask Parameter: PIDController_UpperSaturationLi
   * Referenced by: '<S97>/Saturation'
   */
  5000.0,

  /* Expression: 1000
   * Referenced by: '<S6>/Gain5'
   */
  1000.0,

  /* Expression: 0
   * Referenced by: '<S6>/Zero'
   */
  0.0,

  /* Expression: 0
   * Referenced by: '<Root>/Constant38'
   */
  0.0,

  /* Expression: 1
   * Referenced by: '<Root>/Constant33'
   */
  1.0,

  /* Expression: 0
   * Referenced by: '<Root>/Constant32'
   */
  0.0,

  /* Expression: 1
   * Referenced by: '<Root>/Constant31'
   */
  1.0,

  /* Expression: 0
   * Referenced by: '<Root>/Constant1'
   */
  0.0,

  /* Expression: 999
   * Referenced by: '<Root>/Constant30'
   */
  999.0,

  /* Expression: 0
   * Referenced by: '<S8>/Memory1'
   */
  0.0,

  /* Expression: 0
   * Referenced by: '<S8>/Memory3'
   */
  0.0,

  /* Expression: 0
   * Referenced by: '<S8>/Rate Transition'
   */
  0.0,

  /* Expression: 0
   * Referenced by: '<S8>/Rate Transition1'
   */
  0.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: 200
   * Referenced by: '<S8>/Constant'
   */
  200.0,

  /* Expression: 200
   * Referenced by: '<S8>/Constant1'
   */
  200.0,

  /* Expression: 1/200
   * Referenced by: '<S8>/Gain'
   */
  0.005,

  /* Expression: 1/200
   * Referenced by: '<S8>/Gain1'
   */
  0.005,

  /* Expression: 360/8192
   * Referenced by: '<Root>/Gain1'
   */
  0.0439453125,

  /* Expression: 0
   * Referenced by: '<Root>/Memory'
   */
  0.0,

  /* Expression: 0.7651
   * Referenced by: '<Root>/Spring constant Nm//deg'
   */
  0.7651,

  /* Expression: 0
   * Referenced by: '<S6>/Zero1'
   */
  0.0,

  /* Expression: -1000
   * Referenced by: '<S6>/Gain'
   */
  -1000.0,

  /* Expression: 0.5
   * Referenced by: '<Root>/Nm // deg'
   */
  0.5,

  /* Expression: 1000
   * Referenced by: '<S6>/-FeedbackP2'
   */
  1000.0,

  /* Expression: -30
   * Referenced by: '<Root>/Constant34'
   */
  -30.0,

  /* Expression: 28
   * Referenced by: '<Root>/Constant35'
   */
  28.0,

  /* Expression: -0.1
   * Referenced by: '<Root>/Constant36'
   */
  -0.1,

  /* Expression: 1000
   * Referenced by: '<S6>/-FeedbackP1'
   */
  1000.0,

  /* Expression: -70
   * Referenced by: '<S6>/Dead Zone1'
   */
  -70.0,

  /* Expression: 70
   * Referenced by: '<S6>/Dead Zone1'
   */
  70.0,

  /* Expression: 0.7
   * Referenced by: '<Root>/P1'
   */
  0.7,

  /* Computed Parameter: Integrator_gainval
   * Referenced by: '<S42>/Integrator'
   */
  0.001,

  /* Expression: 0.4
   * Referenced by: '<Root>/I1'
   */
  0.4,

  /* Expression: 0
   * Referenced by: '<S6>/Dead Zone'
   */
  0.0,

  /* Expression: 0
   * Referenced by: '<S6>/Dead Zone'
   */
  0.0,

  /* Computed Parameter: Integrator_gainval_f
   * Referenced by: '<S90>/Integrator'
   */
  0.001,

  /* Expression: 24
   * Referenced by: '<Root>/Sine Wave Function'
   */
  24.0,

  /* Expression: 0
   * Referenced by: '<Root>/Sine Wave Function'
   */
  0.0,

  /* Expression: 0.5 * 6.28
   * Referenced by: '<Root>/Sine Wave Function'
   */
  3.14,

  /* Expression: 0
   * Referenced by: '<Root>/Sine Wave Function'
   */
  0.0,

  /* Expression: 1
   * Referenced by: '<Root>/Gain'
   */
  1.0,

  /* Expression: 9
   * Referenced by: '<S1>/Constant2'
   */
  9.0,

  /* Expression: 0
   * Referenced by: '<S7>/2nd order, 12Hz2'
   */
  0.0,

  /* Expression: 0
   * Referenced by: '<S7>/2nd order, 60Hz'
   */
  0.0,

  /* Expression: 0
   * Referenced by: '<Root>/Switch4'
   */
  0.0,

  /* Expression: 0
   * Referenced by:
   */
  0.0,

  /* Expression: 1024
   * Referenced by: '<Root>/Memory8'
   */
  1024.0,

  /* Expression: 0
   * Referenced by: '<Root>/Memory9'
   */
  0.0,

  /* Computed Parameter: TmpRTBAtEtherCATPDOTransmitInpo
   * Referenced by:
   */
  0U,

  /* Computed Parameter: ManualSwitch11_CurrentSetting
   * Referenced by: '<Root>/Manual Switch11'
   */
  1U,

  /* Computed Parameter: ManualSwitch1_CurrentSetting
   * Referenced by: '<Root>/Manual Switch1'
   */
  0U,

  /* Computed Parameter: ManualSwitch10_CurrentSetting
   * Referenced by: '<S6>/Manual Switch10'
   */
  0U,

  /* Computed Parameter: ManualSwitch10_CurrentSetting_h
   * Referenced by: '<Root>/Manual Switch10'
   */
  1U
};

MotorTorqueControlTest_cal_type *MotorTorqueControlTest_work_cal =
  &MotorTorqueControlTest_cal_impl;
