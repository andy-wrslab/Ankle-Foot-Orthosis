/*
 * MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo.cpp
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

#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo.h"
#include "rtwtypes.h"
#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_private.h"
#include <cstring>

extern "C"
{

#include "rt_nonfinite.h"

}

#include <cmath>
#include "crl_mutex.hpp"
#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_cal.h"
#include "zero_crossing_types.h"

/* Named constants for Chart: '<Root>/Motor Initliazation1' */
const uint8_T MotorTorqueC_IN_NO_ACTIVE_CHILD = 0U;
const uint32_T MotorTorqueControlTes_IN_inits1 = 2U;
const uint32_T MotorTorqueControlTes_IN_inits2 = 3U;
const uint32_T MotorTorqueControlTes_IN_inits3 = 4U;
const uint32_T MotorTorqueControlTest_IN_inits = 1U;

/* Block signals (default storage) */
B_MotorTorqueControlTest_work_T MotorTorqueControlTest_workin_B;

/* Block states (default storage) */
DW_MotorTorqueControlTest_wor_T MotorTorqueControlTest_worki_DW;

/* Previous zero-crossings (trigger) states */
PrevZCX_MotorTorqueControlTes_T MotorTorqueControlTest__PrevZCX;

/* Real-time model */
RT_MODEL_MotorTorqueControlTe_T MotorTorqueControlTest_worki_M_ =
  RT_MODEL_MotorTorqueControlTe_T();
RT_MODEL_MotorTorqueControlTe_T *const MotorTorqueControlTest_worki_M =
  &MotorTorqueControlTest_worki_M_;
void S1_EtherCATInit_callback(void * const ptr_rtm )
{
  int_T status = 1;
  static const char_T *errMsg;
  int_T j;
  static char_T msg[256];
  std::string logfile( "" );           //logFileName );
  std::string DeviceType( "I8254x" );
  mwStateClear( 0 );
  LOG(info,0) << "EtherCAT going to state 8";
  status = slrtEcatInit(0,
                        DeviceType.c_str(),
                        1,
                        1,
                        (unsigned char *)xmlecatArr_0,
                        xmlecatArr_0_count,
                        1,
                        0,
                        logfile.c_str(),
                        0.001,
                        2,
                        8 );
  if (status != XPC_ECAT_OK) {
    if ((((uint32_T)status >> 16) & 0xffff) == 0xffff ) {
      // Our error conditions, negative numbers.
      switch ( status )
      {
       case -10:        // very rare, sg_getEthercatInterface can't be executed!
        errMsg =
          "Speedgoat library files for EtherCAT port identification are not properly installed on the target";
        break;

       case -11:          // rare, sg_getEthercatInterface didn't create eciface
        errMsg = "Ethernet port mapping failed";// eciface didn't get created
        break;

       case -12:
              // common, User entered a 1 based port number that isn't reserved.
        errMsg = "EtherCAT port 1 is not reserved for EtherCAT";
        break;
      }
    } else {
      if ((uint32_T)status == 0x9811000C )
        errMsg =
          "Network port 1 is not accessible to EtherCAT.\nIt is either non-existant or not configured for EtherCAT.";
      else
        errMsg = xpcPrintEtherCATError(0, 0);
    }

    rtmSetErrorStatus(MotorTorqueControlTest_worki_M, errMsg);
    return;
  }
}

/*
 * Output and update for atomic system:
 *    '<S8>/MATLAB Function'
 *    '<S8>/MATLAB Function1'
 */
void MotorTorqueC_MATLABFunction(real_T rtu_sig_in, const real_T rtu_prev_buf
  [200], real_T rtu_N, real_T rtu_prev_updated_idx,
  B_MATLABFunction_MotorTorqueC_T *localB)
{
  real_T r;

  /* MATLAB Function 'Triggered Subsystem6/MATLAB Function': '<S107>:1' */
  /* '<S107>:1:2' */
  std::memcpy(&localB->newbuf[0], &rtu_prev_buf[0], 200U * sizeof(real_T));

  /* '<S107>:1:3' */
  /* '<S107>:1:8' */
  r = rtu_prev_updated_idx;
  if (rtu_N == 0.0) {
    if (rtu_prev_updated_idx == 0.0) {
      r = rtu_N;
    }
  } else if (rtIsNaN(rtu_prev_updated_idx) || rtIsNaN(rtu_N) || rtIsInf
             (rtu_prev_updated_idx)) {
    r = (rtNaN);
  } else if (rtu_prev_updated_idx == 0.0) {
    r = 0.0 / rtu_N;
  } else if (rtIsInf(rtu_N)) {
    if ((rtu_N < 0.0) != (rtu_prev_updated_idx < 0.0)) {
      r = rtu_N;
    }
  } else {
    boolean_T rEQ0;
    r = std::fmod(rtu_prev_updated_idx, rtu_N);
    rEQ0 = (r == 0.0);
    if ((!rEQ0) && (rtu_N > std::floor(rtu_N))) {
      real_T q;
      q = std::abs(rtu_prev_updated_idx / rtu_N);
      rEQ0 = !(std::abs(q - std::floor(q + 0.5)) > 2.2204460492503131E-16 * q);
    }

    if (rEQ0) {
      r = rtu_N * 0.0;
    } else if ((rtu_prev_updated_idx < 0.0) != (rtu_N < 0.0)) {
      r += rtu_N;
    }
  }

  /* '<S107>:1:4' */
  localB->newbuf[static_cast<int32_T>(r + 1.0) - 1] = rtu_sig_in;
  localB->last_updated_idx = r + 1.0;
}

/*
 * Output and update for trigger system:
 *    '<S8>/Triggered Subsystem'
 *    '<S8>/Triggered Subsystem1'
 */
void MotorTor_TriggeredSubsystem(real_T rtu_Trigger, real_T rtu_offset,
  B_TriggeredSubsystem_MotorTor_T *localB, DW_TriggeredSubsystem_MotorTo_T
  *localDW, ZCE_TriggeredSubsystem_MotorT_T *localZCE)
{
  ZCEventType zcEvent;

  /* Outputs for Triggered SubSystem: '<S8>/Triggered Subsystem' incorporates:
   *  TriggerPort: '<S109>/Trigger'
   */
  zcEvent = rt_ZCFcn(RISING_ZERO_CROSSING,&localZCE->TriggeredSubsystem_Trig_ZCE,
                     (rtu_Trigger));
  if (zcEvent != NO_ZCEVENT) {
    /* SignalConversion generated from: '<S109>/offset' */
    localB->offset = rtu_offset;
    localDW->TriggeredSubsystem_SubsysRanBC = 4;
  }

  /* End of Outputs for SubSystem: '<S8>/Triggered Subsystem' */
}

/* Model step function for TID0 */
void MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step0(void) /* Sample time: [0.0s, 0.0s] */
{
  real_T u;
  real_T u1;
  real_T u2;
  int32_T i;
  int8_T wrBufIdx;

  /* Update the flag to indicate when data transfers from
   *  Sample time: [0.001s, 0.0s] to Sample time: [0.005s, 0.0s]  */
  (MotorTorqueControlTest_worki_M->Timing.RateInteraction.TID1_2)++;
  if ((MotorTorqueControlTest_worki_M->Timing.RateInteraction.TID1_2) > 4) {
    MotorTorqueControlTest_worki_M->Timing.RateInteraction.TID1_2 = 0;
  }

  {
    /* user code (Output function Header for TID0) */
    {
      /*------------ S-Function Block: <S1>/EtherCAT Init Process Received Frames ------------*/
      unsigned int data[6]= { 0 };

      int32_T msdata[4] = { 0 };

      xpcEtherCATReadProcessData(0,NULL);
      mwErrorGet((int_T)0,
                 &data[0], &data[1], &data[2], (int *)&data[3], &data[4], (int *)
                 &data[5]);
      memcpy(&MotorTorqueControlTest_workin_B.EtherCATInit[0], data,6*sizeof
             (int32_T));
      mwErrorClear( (int_T)0 );

      // Clear all momentary triggered values
    }

    /* Reset subsysRan breadcrumbs */
    srClearBC
      (MotorTorqueControlTest_worki_DW.TriggeredSubsystem.TriggeredSubsystem_SubsysRanBC);

    /* Gain: '<Root>/Gain1' */
    MotorTorqueControlTest_workin_B.Gain1 =
      MotorTorqueControlTest_work_cal->Gain1_Gain_i * 0.0;

    /* ManualSwitch: '<Root>/Manual Switch11' */
    if (MotorTorqueControlTest_work_cal->ManualSwitch11_CurrentSetting == 1) {
      /* ManualSwitch: '<Root>/Manual Switch11' incorporates:
       *  Constant: '<Root>/Constant32'
       */
      MotorTorqueControlTest_workin_B.ManualSwitch11 =
        MotorTorqueControlTest_work_cal->Constant32_Value;
    } else {
      /* ManualSwitch: '<Root>/Manual Switch11' incorporates:
       *  Constant: '<Root>/Constant31'
       */
      MotorTorqueControlTest_workin_B.ManualSwitch11 =
        MotorTorqueControlTest_work_cal->Constant31_Value;
    }

    /* End of ManualSwitch: '<Root>/Manual Switch11' */

    /* Outputs for Atomic SubSystem: '<Root>/Triggered Subsystem6' */
    /* Memory: '<S8>/Memory1' */
    MotorTorqueControlTest_workin_B.Memory1 =
      MotorTorqueControlTest_worki_DW.Memory1_PreviousInput;

    /* Memory: '<S8>/Memory' */
    std::memcpy(&MotorTorqueControlTest_workin_B.Memory_i[0],
                &MotorTorqueControlTest_worki_DW.Memory_PreviousInput_b[0], 200U
                * sizeof(real_T));

    /* Memory: '<S8>/Memory2' */
    std::memcpy(&MotorTorqueControlTest_workin_B.Memory2[0],
                &MotorTorqueControlTest_worki_DW.Memory2_PreviousInput[0], 200U *
                sizeof(real_T));

    /* Memory: '<S8>/Memory3' */
    MotorTorqueControlTest_workin_B.Memory3 =
      MotorTorqueControlTest_worki_DW.Memory3_PreviousInput;

    /* RateTransition: '<S8>/Rate Transition' */
    if (MotorTorqueControlTest_worki_M->Timing.RateInteraction.TID1_2 == 1) {
      MotorTorqueControlTest_worki_DW.RateTransition_WrBufIdx =
        static_cast<int8_T>
        (MotorTorqueControlTest_worki_DW.RateTransition_WrBufIdx == 0);
    }

    MotorTorqueControlTest_worki_DW.RateTransition_Buf[MotorTorqueControlTest_worki_DW.RateTransition_WrBufIdx]
      = MotorTorqueControlTest_workin_B.Gain1;

    /* End of RateTransition: '<S8>/Rate Transition' */

    /* RateTransition: '<S8>/Rate Transition1' */
    if (MotorTorqueControlTest_worki_M->Timing.RateInteraction.TID1_2 == 1) {
      MotorTorqueControlTest_worki_DW.RateTransition1_WrBufIdx =
        static_cast<int8_T>
        (MotorTorqueControlTest_worki_DW.RateTransition1_WrBufIdx == 0);
    }

    MotorTorqueControlTest_worki_DW.RateTransition1_Buf[MotorTorqueControlTest_worki_DW.RateTransition1_WrBufIdx]
      = 0.0;

    /* End of RateTransition: '<S8>/Rate Transition1' */

    /* RateTransition generated from: '<S8>/Triggered Subsystem' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInp_b);
    MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemIn_bw =
      MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInp_g;
    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInp_b);

    /* RateTransition generated from: '<S8>/Triggered Subsystem' */
    MotorTorqueControlTest_workin_B.TmpRTBAtTriggeredSubsystemInpor =
      MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInpor[MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemIn_bw];

    /* Outputs for Triggered SubSystem: '<S8>/Triggered Subsystem' */
    MotorTor_TriggeredSubsystem(MotorTorqueControlTest_workin_B.ManualSwitch11,
      MotorTorqueControlTest_workin_B.TmpRTBAtTriggeredSubsystemInpor,
      &MotorTorqueControlTest_workin_B.TriggeredSubsystem,
      &MotorTorqueControlTest_worki_DW.TriggeredSubsystem,
      &MotorTorqueControlTest__PrevZCX.TriggeredSubsystem);

    /* End of Outputs for SubSystem: '<S8>/Triggered Subsystem' */

    /* Sum: '<S8>/Sum' */
    MotorTorqueControlTest_workin_B.Sum_p =
      MotorTorqueControlTest_workin_B.Gain1 -
      MotorTorqueControlTest_workin_B.TriggeredSubsystem.offset;

    /* RateTransition generated from: '<S8>/Triggered Subsystem1' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_j);
    MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_e =
      MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_d;
    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_j);

    /* RateTransition generated from: '<S8>/Triggered Subsystem1' */
    MotorTorqueControlTest_workin_B.TmpRTBAtTriggeredSubsystem1Inpo =
      MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1Inpo[MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_e];

    /* Outputs for Triggered SubSystem: '<S8>/Triggered Subsystem1' */
    MotorTor_TriggeredSubsystem(MotorTorqueControlTest_workin_B.ManualSwitch11,
      MotorTorqueControlTest_workin_B.TmpRTBAtTriggeredSubsystem1Inpo,
      &MotorTorqueControlTest_workin_B.TriggeredSubsystem1,
      &MotorTorqueControlTest_worki_DW.TriggeredSubsystem1,
      &MotorTorqueControlTest__PrevZCX.TriggeredSubsystem1);

    /* End of Outputs for SubSystem: '<S8>/Triggered Subsystem1' */

    /* Sum: '<S8>/Sum1' */
    MotorTorqueControlTest_workin_B.Sum1 = 0.0 -
      MotorTorqueControlTest_workin_B.TriggeredSubsystem1.offset;

    /* RateTransition generated from: '<S8>/MATLAB Function1' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_d);
    wrBufIdx = static_cast<int8_T>
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_dg + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }

    if (wrBufIdx ==
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_ha) {
      wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
      if (wrBufIdx == 3) {
        wrBufIdx = 0;
      }
    }

    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_d);
    switch (wrBufIdx) {
     case 0:
      for (i = 0; i < 200; i++) {
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport2_[i] =
          MotorTorqueControlTest_workin_B.Memory2[i];
      }
      break;

     case 1:
      for (i = 0; i < 200; i++) {
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_p[i] =
          MotorTorqueControlTest_workin_B.Memory2[i];
      }
      break;

     case 2:
      for (i = 0; i < 200; i++) {
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_a[i] =
          MotorTorqueControlTest_workin_B.Memory2[i];
      }
      break;
    }

    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_dg = wrBufIdx;

    /* End of RateTransition generated from: '<S8>/MATLAB Function1' */

    /* RateTransition generated from: '<S8>/MATLAB Function1' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_n);
    wrBufIdx = static_cast<int8_T>
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_hu + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }

    if (wrBufIdx ==
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_au) {
      wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
      if (wrBufIdx == 3) {
        wrBufIdx = 0;
      }
    }

    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_n);
    switch (wrBufIdx) {
     case 0:
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport4_ =
        MotorTorqueControlTest_workin_B.Memory3;
      break;

     case 1:
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_h =
        MotorTorqueControlTest_workin_B.Memory3;
      break;

     case 2:
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_j =
        MotorTorqueControlTest_workin_B.Memory3;
      break;
    }

    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_hu = wrBufIdx;

    /* End of RateTransition generated from: '<S8>/MATLAB Function1' */

    /* RateTransition generated from: '<S8>/MATLAB Function1' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_o);
    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_b =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_l;
    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_o);

    /* RateTransition generated from: '<S8>/MATLAB Function1' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Outport2 =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outport2[MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_b];

    /* RateTransition generated from: '<S8>/MATLAB Function' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_d);
    wrBufIdx = static_cast<int8_T>
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_L + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }

    if (wrBufIdx ==
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_R) {
      wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
      if (wrBufIdx == 3) {
        wrBufIdx = 0;
      }
    }

    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_d);
    switch (wrBufIdx) {
     case 0:
      for (i = 0; i < 200; i++) {
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_B[i] =
          MotorTorqueControlTest_workin_B.Memory_i[i];
      }
      break;

     case 1:
      for (i = 0; i < 200; i++) {
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_c[i] =
          MotorTorqueControlTest_workin_B.Memory_i[i];
      }
      break;

     case 2:
      for (i = 0; i < 200; i++) {
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_f[i] =
          MotorTorqueControlTest_workin_B.Memory_i[i];
      }
      break;
    }

    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_L = wrBufIdx;

    /* End of RateTransition generated from: '<S8>/MATLAB Function' */

    /* RateTransition generated from: '<S8>/MATLAB Function' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_m);
    wrBufIdx = static_cast<int8_T>
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_L + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }

    if (wrBufIdx ==
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_R) {
      wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
      if (wrBufIdx == 3) {
        wrBufIdx = 0;
      }
    }

    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_m);
    switch (wrBufIdx) {
     case 0:
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_B =
        MotorTorqueControlTest_workin_B.Memory1;
      break;

     case 1:
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_g =
        MotorTorqueControlTest_workin_B.Memory1;
      break;

     case 2:
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_d =
        MotorTorqueControlTest_workin_B.Memory1;
      break;
    }

    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_L = wrBufIdx;

    /* End of RateTransition generated from: '<S8>/MATLAB Function' */

    /* RateTransition generated from: '<S8>/MATLAB Function' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_h);
    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_l =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_g;
    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_h);

    /* RateTransition generated from: '<S8>/MATLAB Function' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionOutport2 =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport2_[MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_l];

    /* RateTransition generated from: '<S8>/Memory2' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_d0_SEMAP);
    MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_RDBuf =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_LstBufWR;
    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_d0_SEMAP);
    i = MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_RDBuf * 200;
    for (int32_T i_0 = 0; i_0 < 200; i_0++) {
      /* RateTransition generated from: '<S8>/Memory2' */
      MotorTorqueControlTest_workin_B.buffer[i_0] =
        MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_Buf[i_0 + i];
    }

    /* RateTransition generated from: '<S8>/Memory' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.newbuf_d0_SEMAPHORE);
    MotorTorqueControlTest_worki_DW.newbuf_RDBuf =
      MotorTorqueControlTest_worki_DW.newbuf_LstBufWR;
    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.newbuf_d0_SEMAPHORE);
    i = MotorTorqueControlTest_worki_DW.newbuf_RDBuf * 200;
    for (int32_T i_0 = 0; i_0 < 200; i_0++) {
      /* RateTransition generated from: '<S8>/Memory' */
      MotorTorqueControlTest_workin_B.buffer_e[i_0] =
        MotorTorqueControlTest_worki_DW.newbuf_Buf[i_0 + i];
    }

    /* End of Outputs for SubSystem: '<Root>/Triggered Subsystem6' */

    /* S-Function (slecatpdorx): '<S7>/EtherCAT PDO Receive - Current Value from drive2' */
    {
      /*------------ S-Function Block: <S7>/EtherCAT PDO Receive - Current Value from drive2 PDO receive block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      uint8_T *sigOutputPtr = (uint8_T *)
        &MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentVal_ns;
      uint8_T *ecatRxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatRxBufPtr = (uint8_T *)xpcEtherCATgetPDin( 0 );
      bitOffset = 392;
      for (sigIdx=0; sigIdx < 1; sigIdx++) {
        switch ( 4 ) {
         case SS_DOUBLE:
          ((real_T *)sigOutputPtr)[sigIdx] = *((real_T *)(ecatRxBufPtr+bitOffset/
            8));
          break;

         case SS_SINGLE:
          ((real32_T *)sigOutputPtr)[sigIdx] = *((real32_T *)(ecatRxBufPtr+
            bitOffset/8));
          break;

         case SS_INT8:
          if ((bitOffset % 8 == 0) && (16 == 8) && (2 == sizeof(int8_T))) {
            ((int8_T *)sigOutputPtr)[sigIdx] = *((int8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT8:
          if ((bitOffset%8 == 0) && (16 == 8) && (2 == sizeof(uint8_T))) {
            ((uint8_T *)sigOutputPtr)[sigIdx] = *((uint8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_BOOLEAN:
          slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*2,
                             2);
          break;

         case SS_INT16:
          if ((bitOffset%16 == 0) && (16 == 16) && (2 == sizeof(int16_T))) {
            ((int16_T *)sigOutputPtr)[sigIdx] = *((int16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT16:
          if ((bitOffset%16 == 0) && (16 == 16) && (2 == sizeof(uint16_T))) {
            ((uint16_T *)sigOutputPtr)[sigIdx] = *((uint16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_INT32:
          if ((bitOffset%32 == 0) && (16 == 32) && (2 == sizeof(int32_T))) {
            ((int32_T *)sigOutputPtr)[sigIdx] = *((int32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT32:
          if ((bitOffset%32 == 0) && (16 == 32) && (2 == sizeof(uint32_T))) {
            ((uint32_T *)sigOutputPtr)[sigIdx] = *((uint32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         default:
          /* Fatal error, unsupported type. This is checked in getDataSizes, so it should never happen. */
          break;
        }

        bitOffset += 16;
      }
    }

    /* DataTypeConversion: '<S7>/Data Type Conversion5' */
    MotorTorqueControlTest_workin_B.ActualCurrent =
      MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentVal_ns;

    /* S-Function (slecatpdorx): '<S7>/EtherCAT PDO Receive - Current Value from drive3' */
    {
      /*------------ S-Function Block: <S7>/EtherCAT PDO Receive - Current Value from drive3 PDO receive block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      uint8_T *sigOutputPtr = (uint8_T *)
        &MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentValuef;
      uint8_T *ecatRxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatRxBufPtr = (uint8_T *)xpcEtherCATgetPDin( 0 );
      bitOffset = 360;
      for (sigIdx=0; sigIdx < 1; sigIdx++) {
        switch ( 6 ) {
         case SS_DOUBLE:
          ((real_T *)sigOutputPtr)[sigIdx] = *((real_T *)(ecatRxBufPtr+bitOffset/
            8));
          break;

         case SS_SINGLE:
          ((real32_T *)sigOutputPtr)[sigIdx] = *((real32_T *)(ecatRxBufPtr+
            bitOffset/8));
          break;

         case SS_INT8:
          if ((bitOffset % 8 == 0) && (32 == 8) && (4 == sizeof(int8_T))) {
            ((int8_T *)sigOutputPtr)[sigIdx] = *((int8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_UINT8:
          if ((bitOffset%8 == 0) && (32 == 8) && (4 == sizeof(uint8_T))) {
            ((uint8_T *)sigOutputPtr)[sigIdx] = *((uint8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_BOOLEAN:
          slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*4,
                             4);
          break;

         case SS_INT16:
          if ((bitOffset%16 == 0) && (32 == 16) && (4 == sizeof(int16_T))) {
            ((int16_T *)sigOutputPtr)[sigIdx] = *((int16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_UINT16:
          if ((bitOffset%16 == 0) && (32 == 16) && (4 == sizeof(uint16_T))) {
            ((uint16_T *)sigOutputPtr)[sigIdx] = *((uint16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_INT32:
          if ((bitOffset%32 == 0) && (32 == 32) && (4 == sizeof(int32_T))) {
            ((int32_T *)sigOutputPtr)[sigIdx] = *((int32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_UINT32:
          if ((bitOffset%32 == 0) && (32 == 32) && (4 == sizeof(uint32_T))) {
            ((uint32_T *)sigOutputPtr)[sigIdx] = *((uint32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         default:
          /* Fatal error, unsupported type. This is checked in getDataSizes, so it should never happen. */
          break;
        }

        bitOffset += 32;
      }
    }

    /* DataTypeConversion: '<S7>/Data Type Conversion2' */
    MotorTorqueControlTest_workin_B.ActualVelocity =
      MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentValuef;

    /* S-Function (slecatpdorx): '<S1>/EtherCAT PDO Receive' */
    {
      /*------------ S-Function Block: <S1>/EtherCAT PDO Receive PDO receive block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      uint8_T *sigOutputPtr = (uint8_T *)
        &MotorTorqueControlTest_workin_B.EtherCATPDOReceive;
      uint8_T *ecatRxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatRxBufPtr = (uint8_T *)xpcEtherCATgetPDin( 0 );
      bitOffset = 312;
      for (sigIdx=0; sigIdx < 1; sigIdx++) {
        switch ( 5 ) {
         case SS_DOUBLE:
          ((real_T *)sigOutputPtr)[sigIdx] = *((real_T *)(ecatRxBufPtr+bitOffset/
            8));
          break;

         case SS_SINGLE:
          ((real32_T *)sigOutputPtr)[sigIdx] = *((real32_T *)(ecatRxBufPtr+
            bitOffset/8));
          break;

         case SS_INT8:
          if ((bitOffset % 8 == 0) && (16 == 8) && (2 == sizeof(int8_T))) {
            ((int8_T *)sigOutputPtr)[sigIdx] = *((int8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT8:
          if ((bitOffset%8 == 0) && (16 == 8) && (2 == sizeof(uint8_T))) {
            ((uint8_T *)sigOutputPtr)[sigIdx] = *((uint8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_BOOLEAN:
          slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*2,
                             2);
          break;

         case SS_INT16:
          if ((bitOffset%16 == 0) && (16 == 16) && (2 == sizeof(int16_T))) {
            ((int16_T *)sigOutputPtr)[sigIdx] = *((int16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT16:
          if ((bitOffset%16 == 0) && (16 == 16) && (2 == sizeof(uint16_T))) {
            ((uint16_T *)sigOutputPtr)[sigIdx] = *((uint16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_INT32:
          if ((bitOffset%32 == 0) && (16 == 32) && (2 == sizeof(int32_T))) {
            ((int32_T *)sigOutputPtr)[sigIdx] = *((int32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT32:
          if ((bitOffset%32 == 0) && (16 == 32) && (2 == sizeof(uint32_T))) {
            ((uint32_T *)sigOutputPtr)[sigIdx] = *((uint32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         default:
          /* Fatal error, unsupported type. This is checked in getDataSizes, so it should never happen. */
          break;
        }

        bitOffset += 16;
      }
    }

    /* Memory: '<Root>/Memory' */
    MotorTorqueControlTest_workin_B.Memory =
      MotorTorqueControlTest_worki_DW.Memory_PreviousInput;

    /* MATLAB Function: '<Root>/MATLAB Function' */
    u = MotorTorqueControlTest_workin_B.Sum_p;

    /* MATLAB Function 'MATLAB Function': '<S2>:1' */
    if (std::abs(MotorTorqueControlTest_workin_B.Memory -
                 MotorTorqueControlTest_workin_B.Sum_p) > 1.0) {
      /* '<S2>:1:2' */
      /* '<S2>:1:3' */
      u = MotorTorqueControlTest_workin_B.Memory;
    }

    /* '<S2>:1:7' */
    MotorTorqueControlTest_workin_B.y = u;

    /* End of MATLAB Function: '<Root>/MATLAB Function' */

    /* Product: '<Root>/Product' incorporates:
     *  Constant: '<Root>/Spring constant Nm//deg'
     */
    MotorTorqueControlTest_workin_B.ActualTorque =
      MotorTorqueControlTest_workin_B.y *
      MotorTorqueControlTest_work_cal->SpringconstantNmdeg_Value;

    /* Gain: '<S6>/Gain' incorporates:
     *  Constant: '<S6>/Zero1'
     */
    MotorTorqueControlTest_workin_B.DesiredVelocity_mRPM =
      MotorTorqueControlTest_work_cal->Gain_Gain_j *
      MotorTorqueControlTest_work_cal->Zero1_Value;

    /* DataTypeConversion: '<S6>/Data Type Conversion1' */
    u = std::floor(MotorTorqueControlTest_workin_B.DesiredVelocity_mRPM);
    if (rtIsNaN(u) || rtIsInf(u)) {
      u = 0.0;
    } else {
      u = std::fmod(u, 4.294967296E+9);
    }

    /* DataTypeConversion: '<S6>/Data Type Conversion1' */
    MotorTorqueControlTest_workin_B.DataTypeConversion1 = u < 0.0 ? -
      static_cast<int32_T>(static_cast<uint32_T>(-u)) : static_cast<int32_T>(
      static_cast<uint32_T>(u));

    /* S-Function (slecatpdotx): '<S6>/EtherCAT PDO Transmit - Target Torque' */
    {
      /*------------ S-Function Block: <S6>/EtherCAT PDO Transmit - Target Torque PDO transmit block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      int_T i;
      uint8_T *sigInputPtr = (uint8_T *)
        &MotorTorqueControlTest_workin_B.DataTypeConversion1;
      uint8_T *ecatTxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatTxBufPtr = (uint8_T *)xpcEtherCATgetPDout( 0 );
      bitOffset = 328;
      for (i = 0; i < 1; i++) {
        switch ( 6 ){
         case SS_DOUBLE:
          *((real_T *)(ecatTxBufPtr+bitOffset/8)) = ((real_T *)sigInputPtr)[i];
          break;

         case SS_SINGLE:
          *((real32_T *)(ecatTxBufPtr+bitOffset/8)) = ((real32_T *)sigInputPtr)
            [i];
          break;

         case SS_INT8:
          if ((32 == 8) && (bitOffset%8 == 0)) {
            *((int8_T *)(ecatTxBufPtr+bitOffset/8)) = ((int8_T *)sigInputPtr)[i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 32, (uint32_T)
                               (*((int8_T *)sigInputPtr)));
          }
          break;

         case SS_UINT8:
          if ((32 == 8) && (bitOffset%8 == 0)) {
            *((uint8_T *)(ecatTxBufPtr+bitOffset/8)) = ((uint8_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 32, (uint32_T)
                               (*((uint8_T *)sigInputPtr)));
          }
          break;

         case SS_BOOLEAN:
          if ((32 == 8) && (bitOffset%8 == 0)) {
            *((int8_T *)(ecatTxBufPtr+bitOffset/8)) = ((int8_T *)sigInputPtr)[i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 32, (uint32_T)
                               (*((int8_T *)sigInputPtr)));
          }
          break;

         case SS_INT16:
          if ((32 == 16) && (bitOffset%16 == 0)) {
            *((int16_T *)(ecatTxBufPtr+bitOffset/8)) = ((int16_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 32, (uint32_T)
                               (*((int16_T *)sigInputPtr)));
          }
          break;

         case SS_UINT16:
          if ((32 == 16) && (bitOffset%16 == 0)) {
            *((uint16_T *)(ecatTxBufPtr+bitOffset/8)) =((uint16_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 32, (uint32_T)
                               (*((uint16_T *)sigInputPtr)));
          }
          break;

         case SS_INT32:
          if ((32 == 32) && (bitOffset%32 == 0)) {
            *((int32_T *)(ecatTxBufPtr+bitOffset/8)) = ((int32_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 32, (uint32_T)
                               (*((int32_T *)sigInputPtr)));
          }
          break;

         case SS_UINT32:
          if ((32 == 32) && (bitOffset%32 == 0)) {
            *((uint32_T *)(ecatTxBufPtr+bitOffset/8)) = ((uint32_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 32, (uint32_T)
                               (*((uint32_T *)sigInputPtr)));
          }
          break;

         default:
          /* Fatal error. Should never happen as this is checked in mdlStart. */
          break;
        }

        bitOffset += 32;
      }
    }

    /* Product: '<Root>/Product1' incorporates:
     *  Constant: '<Root>/Nm // deg'
     */
    MotorTorqueControlTest_workin_B.Product1 =
      MotorTorqueControlTest_workin_B.Sum1 *
      MotorTorqueControlTest_work_cal->Nmdeg_Value;

    /* ManualSwitch: '<Root>/Manual Switch1' */
    if (MotorTorqueControlTest_work_cal->ManualSwitch1_CurrentSetting == 1) {
      /* ManualSwitch: '<Root>/Manual Switch1' */
      MotorTorqueControlTest_workin_B.ManualSwitch1 =
        MotorTorqueControlTest_workin_B.Product1;
    } else {
      /* ManualSwitch: '<Root>/Manual Switch1' incorporates:
       *  Constant: '<Root>/Constant1'
       */
      MotorTorqueControlTest_workin_B.ManualSwitch1 =
        MotorTorqueControlTest_work_cal->Constant1_Value;
    }

    /* End of ManualSwitch: '<Root>/Manual Switch1' */

    /* Gain: '<S6>/-FeedbackP2' */
    MotorTorqueControlTest_workin_B.Feedback_signal_torque =
      MotorTorqueControlTest_work_cal->FeedbackP2_Gain *
      MotorTorqueControlTest_workin_B.ManualSwitch1;

    /* MATLAB Function: '<Root>/MATLAB Function3' incorporates:
     *  Constant: '<Root>/Constant34'
     *  Constant: '<Root>/Constant35'
     *  Constant: '<Root>/Constant36'
     */
    /* MATLAB Function 'MATLAB Function3': '<S3>:1' */
    /* '<S3>:1:2' */
    /* '<S3>:1:4' */
    /* '<S3>:1:5' */
    if (MotorTorqueControlTest_workin_B.Sum1 <=
        MotorTorqueControlTest_work_cal->Constant34_Value + 5.0) {
      /* '<S3>:1:7' */
      /* '<S3>:1:8' */
      MotorTorqueControlTest_workin_B.tau =
        (MotorTorqueControlTest_workin_B.Sum1 -
         (MotorTorqueControlTest_work_cal->Constant34_Value + 5.0)) *
        -MotorTorqueControlTest_work_cal->Constant36_Value;
    } else if (MotorTorqueControlTest_workin_B.Sum1 >=
               MotorTorqueControlTest_work_cal->Constant35_Value - 5.0) {
      /* '<S3>:1:10' */
      /* '<S3>:1:11' */
      MotorTorqueControlTest_workin_B.tau =
        (MotorTorqueControlTest_workin_B.Sum1 -
         (MotorTorqueControlTest_work_cal->Constant35_Value - 5.0)) *
        -MotorTorqueControlTest_work_cal->Constant36_Value;
    } else {
      /* '<S3>:1:13' */
      MotorTorqueControlTest_workin_B.tau = 0.0;
    }

    /* End of MATLAB Function: '<Root>/MATLAB Function3' */

    /* ManualSwitch: '<S6>/Manual Switch10' */
    if (MotorTorqueControlTest_work_cal->ManualSwitch10_CurrentSetting == 1) {
      /* Gain: '<S6>/Gain5' */
      MotorTorqueControlTest_workin_B.Gain5 =
        MotorTorqueControlTest_work_cal->Gain5_Gain *
        MotorTorqueControlTest_workin_B.tau;

      /* ManualSwitch: '<S6>/Manual Switch10' */
      MotorTorqueControlTest_workin_B.BumperTorque =
        MotorTorqueControlTest_workin_B.Gain5;
    } else {
      /* ManualSwitch: '<S6>/Manual Switch10' incorporates:
       *  Constant: '<S6>/Zero'
       */
      MotorTorqueControlTest_workin_B.BumperTorque =
        MotorTorqueControlTest_work_cal->Zero_Value;
    }

    /* End of ManualSwitch: '<S6>/Manual Switch10' */

    /* Gain: '<S6>/-FeedbackP1' */
    MotorTorqueControlTest_workin_B.FeedbackP1 =
      MotorTorqueControlTest_work_cal->FeedbackP1_Gain *
      MotorTorqueControlTest_workin_B.ActualTorque;

    /* Sum: '<S6>/Sum' */
    MotorTorqueControlTest_workin_B.torque_error =
      (MotorTorqueControlTest_workin_B.BumperTorque -
       MotorTorqueControlTest_workin_B.FeedbackP1) +
      MotorTorqueControlTest_workin_B.Feedback_signal_torque;

    /* DeadZone: '<S6>/Dead Zone1' */
    if (MotorTorqueControlTest_workin_B.torque_error >
        MotorTorqueControlTest_work_cal->DeadZone1_End) {
      /* DeadZone: '<S6>/Dead Zone1' */
      MotorTorqueControlTest_workin_B.DeadZone1 =
        MotorTorqueControlTest_workin_B.torque_error -
        MotorTorqueControlTest_work_cal->DeadZone1_End;
    } else if (MotorTorqueControlTest_workin_B.torque_error >=
               MotorTorqueControlTest_work_cal->DeadZone1_Start) {
      /* DeadZone: '<S6>/Dead Zone1' */
      MotorTorqueControlTest_workin_B.DeadZone1 = 0.0;
    } else {
      /* DeadZone: '<S6>/Dead Zone1' */
      MotorTorqueControlTest_workin_B.DeadZone1 =
        MotorTorqueControlTest_workin_B.torque_error -
        MotorTorqueControlTest_work_cal->DeadZone1_Start;
    }

    /* End of DeadZone: '<S6>/Dead Zone1' */
    /* Product: '<S47>/PProd Out' incorporates:
     *  Constant: '<Root>/P1'
     */
    MotorTorqueControlTest_workin_B.PProdOut =
      MotorTorqueControlTest_workin_B.DeadZone1 *
      MotorTorqueControlTest_work_cal->P1_Value;

    /* DiscreteIntegrator: '<S42>/Integrator' */
    MotorTorqueControlTest_workin_B.Integrator =
      MotorTorqueControlTest_worki_DW.Integrator_DSTATE;

    /* Sum: '<S51>/Sum' */
    MotorTorqueControlTest_workin_B.Sum =
      MotorTorqueControlTest_workin_B.PProdOut +
      MotorTorqueControlTest_workin_B.Integrator;

    /* Product: '<S39>/IProd Out' incorporates:
     *  Constant: '<Root>/I1'
     */
    MotorTorqueControlTest_workin_B.IProdOut =
      MotorTorqueControlTest_workin_B.DeadZone1 *
      MotorTorqueControlTest_work_cal->I1_Value;

    /* DeadZone: '<S6>/Dead Zone' */
    if (MotorTorqueControlTest_work_cal->DeadZone_End < 0.0) {
      /* DeadZone: '<S6>/Dead Zone' */
      MotorTorqueControlTest_workin_B.DeadZone = 0.0 -
        MotorTorqueControlTest_work_cal->DeadZone_End;
    } else if (MotorTorqueControlTest_work_cal->DeadZone_Start <= 0.0) {
      /* DeadZone: '<S6>/Dead Zone' */
      MotorTorqueControlTest_workin_B.DeadZone = 0.0;
    } else {
      /* DeadZone: '<S6>/Dead Zone' */
      MotorTorqueControlTest_workin_B.DeadZone = 0.0 -
        MotorTorqueControlTest_work_cal->DeadZone_Start;
    }

    /* End of DeadZone: '<S6>/Dead Zone' */
    /* Product: '<S95>/PProd Out' */
    MotorTorqueControlTest_workin_B.PProdOut_k =
      MotorTorqueControlTest_workin_B.DeadZone * 0.0;

    /* DiscreteIntegrator: '<S90>/Integrator' */
    if (MotorTorqueControlTest_worki_DW.Integrator_PrevResetState == 1) {
      MotorTorqueControlTest_worki_DW.Integrator_DSTATE_l =
        MotorTorqueControlTest_work_cal->PIDController_InitialConditionF;
    }

    /* DiscreteIntegrator: '<S90>/Integrator' */
    MotorTorqueControlTest_workin_B.Integrator_j =
      MotorTorqueControlTest_worki_DW.Integrator_DSTATE_l;

    /* Sum: '<S99>/Sum' */
    MotorTorqueControlTest_workin_B.Sum_o =
      MotorTorqueControlTest_workin_B.PProdOut_k +
      MotorTorqueControlTest_workin_B.Integrator_j;

    /* Saturate: '<S97>/Saturation' */
    u = MotorTorqueControlTest_workin_B.Sum_o;
    u1 = MotorTorqueControlTest_work_cal->PIDController_LowerSaturationLi;
    u2 = MotorTorqueControlTest_work_cal->PIDController_UpperSaturationLi;
    if (u > u2) {
      /* Saturate: '<S97>/Saturation' */
      MotorTorqueControlTest_workin_B.Saturation = u2;
    } else if (u < u1) {
      /* Saturate: '<S97>/Saturation' */
      MotorTorqueControlTest_workin_B.Saturation = u1;
    } else {
      /* Saturate: '<S97>/Saturation' */
      MotorTorqueControlTest_workin_B.Saturation = u;
    }

    /* End of Saturate: '<S97>/Saturation' */
    /* Product: '<S87>/IProd Out' */
    MotorTorqueControlTest_workin_B.IProdOut_l =
      MotorTorqueControlTest_workin_B.DeadZone * 0.0;

    /* Sin: '<Root>/Sine Wave Function' */
    MotorTorqueControlTest_workin_B.SineWaveFunction = std::sin
      (MotorTorqueControlTest_work_cal->SineWaveFunction_Freq *
       MotorTorqueControlTest_worki_M->Timing.t[0] +
       MotorTorqueControlTest_work_cal->SineWaveFunction_Phase) *
      MotorTorqueControlTest_work_cal->SineWaveFunction_Amp +
      MotorTorqueControlTest_work_cal->SineWaveFunction_Bias;

    /* Gain: '<Root>/Gain' */
    MotorTorqueControlTest_workin_B.AssistiveTorque =
      MotorTorqueControlTest_work_cal->Gain_Gain_b *
      MotorTorqueControlTest_workin_B.Product1;

    /* RateTransition generated from: '<S1>/EtherCAT PDO Transmit' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitInpo);
    MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitIn_d =
      MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitIn_a;
    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitInpo);

    /* RateTransition generated from: '<S1>/EtherCAT PDO Transmit' */
    MotorTorqueControlTest_workin_B.TmpRTBAtEtherCATPDOTransmitInpo =
      MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitIn_n[MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitIn_d];

    /* S-Function (slecatpdotx): '<S1>/EtherCAT PDO Transmit' */
    {
      /*------------ S-Function Block: <S1>/EtherCAT PDO Transmit PDO transmit block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      int_T i;
      uint8_T *sigInputPtr = (uint8_T *)
        &MotorTorqueControlTest_workin_B.TmpRTBAtEtherCATPDOTransmitInpo;
      uint8_T *ecatTxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatTxBufPtr = (uint8_T *)xpcEtherCATgetPDout( 0 );
      bitOffset = 312;
      for (i = 0; i < 1; i++) {
        switch ( 5 ){
         case SS_DOUBLE:
          *((real_T *)(ecatTxBufPtr+bitOffset/8)) = ((real_T *)sigInputPtr)[i];
          break;

         case SS_SINGLE:
          *((real32_T *)(ecatTxBufPtr+bitOffset/8)) = ((real32_T *)sigInputPtr)
            [i];
          break;

         case SS_INT8:
          if ((16 == 8) && (bitOffset%8 == 0)) {
            *((int8_T *)(ecatTxBufPtr+bitOffset/8)) = ((int8_T *)sigInputPtr)[i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((int8_T *)sigInputPtr)));
          }
          break;

         case SS_UINT8:
          if ((16 == 8) && (bitOffset%8 == 0)) {
            *((uint8_T *)(ecatTxBufPtr+bitOffset/8)) = ((uint8_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((uint8_T *)sigInputPtr)));
          }
          break;

         case SS_BOOLEAN:
          if ((16 == 8) && (bitOffset%8 == 0)) {
            *((int8_T *)(ecatTxBufPtr+bitOffset/8)) = ((int8_T *)sigInputPtr)[i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((int8_T *)sigInputPtr)));
          }
          break;

         case SS_INT16:
          if ((16 == 16) && (bitOffset%16 == 0)) {
            *((int16_T *)(ecatTxBufPtr+bitOffset/8)) = ((int16_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((int16_T *)sigInputPtr)));
          }
          break;

         case SS_UINT16:
          if ((16 == 16) && (bitOffset%16 == 0)) {
            *((uint16_T *)(ecatTxBufPtr+bitOffset/8)) =((uint16_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((uint16_T *)sigInputPtr)));
          }
          break;

         case SS_INT32:
          if ((16 == 32) && (bitOffset%32 == 0)) {
            *((int32_T *)(ecatTxBufPtr+bitOffset/8)) = ((int32_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((int32_T *)sigInputPtr)));
          }
          break;

         case SS_UINT32:
          if ((16 == 32) && (bitOffset%32 == 0)) {
            *((uint32_T *)(ecatTxBufPtr+bitOffset/8)) = ((uint32_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((uint32_T *)sigInputPtr)));
          }
          break;

         default:
          /* Fatal error. Should never happen as this is checked in mdlStart. */
          break;
        }

        bitOffset += 16;
      }
    }

    /* DataTypeConversion: '<S1>/Data Type Conversion1' incorporates:
     *  Constant: '<S1>/Constant2'
     */
    u = std::floor(MotorTorqueControlTest_work_cal->Constant2_Value);
    if (rtIsNaN(u) || rtIsInf(u)) {
      u = 0.0;
    } else {
      u = std::fmod(u, 65536.0);
    }

    /* DataTypeConversion: '<S1>/Data Type Conversion1' */
    MotorTorqueControlTest_workin_B.DataTypeConversion1_b = static_cast<uint16_T>
      (u < 0.0 ? static_cast<int32_T>(static_cast<uint16_T>(-static_cast<int16_T>
         (static_cast<uint16_T>(-u)))) : static_cast<int32_T>
       (static_cast<uint16_T>(u)));

    /* S-Function (slecatpdotx): '<S1>/EtherCAT PDO Transmit1' */
    {
      /*------------ S-Function Block: <S1>/EtherCAT PDO Transmit1 PDO transmit block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      int_T i;
      uint8_T *sigInputPtr = (uint8_T *)
        &MotorTorqueControlTest_workin_B.DataTypeConversion1_b;
      uint8_T *ecatTxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatTxBufPtr = (uint8_T *)xpcEtherCATgetPDout( 0 );
      bitOffset = 360;
      for (i = 0; i < 1; i++) {
        switch ( 5 ){
         case SS_DOUBLE:
          *((real_T *)(ecatTxBufPtr+bitOffset/8)) = ((real_T *)sigInputPtr)[i];
          break;

         case SS_SINGLE:
          *((real32_T *)(ecatTxBufPtr+bitOffset/8)) = ((real32_T *)sigInputPtr)
            [i];
          break;

         case SS_INT8:
          if ((16 == 8) && (bitOffset%8 == 0)) {
            *((int8_T *)(ecatTxBufPtr+bitOffset/8)) = ((int8_T *)sigInputPtr)[i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((int8_T *)sigInputPtr)));
          }
          break;

         case SS_UINT8:
          if ((16 == 8) && (bitOffset%8 == 0)) {
            *((uint8_T *)(ecatTxBufPtr+bitOffset/8)) = ((uint8_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((uint8_T *)sigInputPtr)));
          }
          break;

         case SS_BOOLEAN:
          if ((16 == 8) && (bitOffset%8 == 0)) {
            *((int8_T *)(ecatTxBufPtr+bitOffset/8)) = ((int8_T *)sigInputPtr)[i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((int8_T *)sigInputPtr)));
          }
          break;

         case SS_INT16:
          if ((16 == 16) && (bitOffset%16 == 0)) {
            *((int16_T *)(ecatTxBufPtr+bitOffset/8)) = ((int16_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((int16_T *)sigInputPtr)));
          }
          break;

         case SS_UINT16:
          if ((16 == 16) && (bitOffset%16 == 0)) {
            *((uint16_T *)(ecatTxBufPtr+bitOffset/8)) =((uint16_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((uint16_T *)sigInputPtr)));
          }
          break;

         case SS_INT32:
          if ((16 == 32) && (bitOffset%32 == 0)) {
            *((int32_T *)(ecatTxBufPtr+bitOffset/8)) = ((int32_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((int32_T *)sigInputPtr)));
          }
          break;

         case SS_UINT32:
          if ((16 == 32) && (bitOffset%32 == 0)) {
            *((uint32_T *)(ecatTxBufPtr+bitOffset/8)) = ((uint32_T *)sigInputPtr)
              [i];
          } else {
            slrtEcatCopyBitsTx((uint8_T *)ecatTxBufPtr, bitOffset, 16, (uint32_T)
                               (*((uint32_T *)sigInputPtr)));
          }
          break;

         default:
          /* Fatal error. Should never happen as this is checked in mdlStart. */
          break;
        }

        bitOffset += 16;
      }
    }

    /* S-Function (slecatgetstate): '<S1>/EtherCAT Get State' */
    {
      /*------------ S-Function Block: <S1>/EtherCAT Get State Get State for  ------------*/
      *&MotorTorqueControlTest_workin_B.EtherCATGetState = xpcEtherCATgetState
        ( 0 );
    }

    /* ManualSwitch: '<Root>/Manual Switch10' */
    if (MotorTorqueControlTest_work_cal->ManualSwitch10_CurrentSetting_h == 1) {
      /* ManualSwitch: '<Root>/Manual Switch10' incorporates:
       *  Constant: '<Root>/Constant38'
       */
      MotorTorqueControlTest_workin_B.ManualSwitch10 =
        MotorTorqueControlTest_work_cal->Constant38_Value;
    } else {
      /* ManualSwitch: '<Root>/Manual Switch10' incorporates:
       *  Constant: '<Root>/Constant33'
       */
      MotorTorqueControlTest_workin_B.ManualSwitch10 =
        MotorTorqueControlTest_work_cal->Constant33_Value;
    }

    /* End of ManualSwitch: '<Root>/Manual Switch10' */
    /* S-Function (slecatpdorx): '<S7>/EtherCAT PDO Receive - Current Value from drive4' */
    {
      /*------------ S-Function Block: <S7>/EtherCAT PDO Receive - Current Value from drive4 PDO receive block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      uint8_T *sigOutputPtr = (uint8_T *)
        &MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentValu_p;
      uint8_T *ecatRxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatRxBufPtr = (uint8_T *)xpcEtherCATgetPDin( 0 );
      bitOffset = 408;
      for (sigIdx=0; sigIdx < 1; sigIdx++) {
        switch ( 6 ) {
         case SS_DOUBLE:
          ((real_T *)sigOutputPtr)[sigIdx] = *((real_T *)(ecatRxBufPtr+bitOffset/
            8));
          break;

         case SS_SINGLE:
          ((real32_T *)sigOutputPtr)[sigIdx] = *((real32_T *)(ecatRxBufPtr+
            bitOffset/8));
          break;

         case SS_INT8:
          if ((bitOffset % 8 == 0) && (32 == 8) && (4 == sizeof(int8_T))) {
            ((int8_T *)sigOutputPtr)[sigIdx] = *((int8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_UINT8:
          if ((bitOffset%8 == 0) && (32 == 8) && (4 == sizeof(uint8_T))) {
            ((uint8_T *)sigOutputPtr)[sigIdx] = *((uint8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_BOOLEAN:
          slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*4,
                             4);
          break;

         case SS_INT16:
          if ((bitOffset%16 == 0) && (32 == 16) && (4 == sizeof(int16_T))) {
            ((int16_T *)sigOutputPtr)[sigIdx] = *((int16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_UINT16:
          if ((bitOffset%16 == 0) && (32 == 16) && (4 == sizeof(uint16_T))) {
            ((uint16_T *)sigOutputPtr)[sigIdx] = *((uint16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_INT32:
          if ((bitOffset%32 == 0) && (32 == 32) && (4 == sizeof(int32_T))) {
            ((int32_T *)sigOutputPtr)[sigIdx] = *((int32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_UINT32:
          if ((bitOffset%32 == 0) && (32 == 32) && (4 == sizeof(uint32_T))) {
            ((uint32_T *)sigOutputPtr)[sigIdx] = *((uint32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         default:
          /* Fatal error, unsupported type. This is checked in getDataSizes, so it should never happen. */
          break;
        }

        bitOffset += 32;
      }
    }

    /* DataTypeConversion: '<S7>/Data Type Conversion7' */
    MotorTorqueControlTest_workin_B.DemandVelocity =
      MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentValu_p;

    /* S-Function (slecatpdorx): '<S7>/EtherCAT PDO Receive - Current Value from drive5' */
    {
      /*------------ S-Function Block: <S7>/EtherCAT PDO Receive - Current Value from drive5 PDO receive block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      uint8_T *sigOutputPtr = (uint8_T *)
        &MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentValu_c;
      uint8_T *ecatRxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatRxBufPtr = (uint8_T *)xpcEtherCATgetPDin( 0 );
      bitOffset = 440;
      for (sigIdx=0; sigIdx < 1; sigIdx++) {
        switch ( 6 ) {
         case SS_DOUBLE:
          ((real_T *)sigOutputPtr)[sigIdx] = *((real_T *)(ecatRxBufPtr+bitOffset/
            8));
          break;

         case SS_SINGLE:
          ((real32_T *)sigOutputPtr)[sigIdx] = *((real32_T *)(ecatRxBufPtr+
            bitOffset/8));
          break;

         case SS_INT8:
          if ((bitOffset % 8 == 0) && (32 == 8) && (4 == sizeof(int8_T))) {
            ((int8_T *)sigOutputPtr)[sigIdx] = *((int8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_UINT8:
          if ((bitOffset%8 == 0) && (32 == 8) && (4 == sizeof(uint8_T))) {
            ((uint8_T *)sigOutputPtr)[sigIdx] = *((uint8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_BOOLEAN:
          slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*4,
                             4);
          break;

         case SS_INT16:
          if ((bitOffset%16 == 0) && (32 == 16) && (4 == sizeof(int16_T))) {
            ((int16_T *)sigOutputPtr)[sigIdx] = *((int16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_UINT16:
          if ((bitOffset%16 == 0) && (32 == 16) && (4 == sizeof(uint16_T))) {
            ((uint16_T *)sigOutputPtr)[sigIdx] = *((uint16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_INT32:
          if ((bitOffset%32 == 0) && (32 == 32) && (4 == sizeof(int32_T))) {
            ((int32_T *)sigOutputPtr)[sigIdx] = *((int32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         case SS_UINT32:
          if ((bitOffset%32 == 0) && (32 == 32) && (4 == sizeof(uint32_T))) {
            ((uint32_T *)sigOutputPtr)[sigIdx] = *((uint32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 32, sigOutputPtr+sigIdx*
                               4, 4);
          }
          break;

         default:
          /* Fatal error, unsupported type. This is checked in getDataSizes, so it should never happen. */
          break;
        }

        bitOffset += 32;
      }
    }

    /* DataTypeConversion: '<S7>/Data Type Conversion6' */
    MotorTorqueControlTest_workin_B.DemandPosition =
      MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentValu_c;

    /* S-Function (slecatpdorx): '<S7>/EtherCAT PDO Receive - Current Value from drive6' */
    {
      /*------------ S-Function Block: <S7>/EtherCAT PDO Receive - Current Value from drive6 PDO receive block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      uint8_T *sigOutputPtr = (uint8_T *)
        &MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentValu_d;
      uint8_T *ecatRxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatRxBufPtr = (uint8_T *)xpcEtherCATgetPDin( 0 );
      bitOffset = 504;
      for (sigIdx=0; sigIdx < 1; sigIdx++) {
        switch ( 5 ) {
         case SS_DOUBLE:
          ((real_T *)sigOutputPtr)[sigIdx] = *((real_T *)(ecatRxBufPtr+bitOffset/
            8));
          break;

         case SS_SINGLE:
          ((real32_T *)sigOutputPtr)[sigIdx] = *((real32_T *)(ecatRxBufPtr+
            bitOffset/8));
          break;

         case SS_INT8:
          if ((bitOffset % 8 == 0) && (16 == 8) && (2 == sizeof(int8_T))) {
            ((int8_T *)sigOutputPtr)[sigIdx] = *((int8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT8:
          if ((bitOffset%8 == 0) && (16 == 8) && (2 == sizeof(uint8_T))) {
            ((uint8_T *)sigOutputPtr)[sigIdx] = *((uint8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_BOOLEAN:
          slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*2,
                             2);
          break;

         case SS_INT16:
          if ((bitOffset%16 == 0) && (16 == 16) && (2 == sizeof(int16_T))) {
            ((int16_T *)sigOutputPtr)[sigIdx] = *((int16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT16:
          if ((bitOffset%16 == 0) && (16 == 16) && (2 == sizeof(uint16_T))) {
            ((uint16_T *)sigOutputPtr)[sigIdx] = *((uint16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_INT32:
          if ((bitOffset%32 == 0) && (16 == 32) && (2 == sizeof(int32_T))) {
            ((int32_T *)sigOutputPtr)[sigIdx] = *((int32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT32:
          if ((bitOffset%32 == 0) && (16 == 32) && (2 == sizeof(uint32_T))) {
            ((uint32_T *)sigOutputPtr)[sigIdx] = *((uint32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         default:
          /* Fatal error, unsupported type. This is checked in getDataSizes, so it should never happen. */
          break;
        }

        bitOffset += 16;
      }
    }

    /* DataTypeConversion: '<S7>/Data Type Conversion8' */
    MotorTorqueControlTest_workin_B.DemandCurrent = static_cast<int16_T>
      (MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentValu_d);

    /* S-Function (slecatpdorx): '<S7>/EtherCAT PDO Receive - Current Value from drive7' */
    {
      /*------------ S-Function Block: <S7>/EtherCAT PDO Receive - Current Value from drive7 PDO receive block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      uint8_T *sigOutputPtr = (uint8_T *)
        &MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentValu_n;
      uint8_T *ecatRxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatRxBufPtr = (uint8_T *)xpcEtherCATgetPDin( 0 );
      bitOffset = 472;
      for (sigIdx=0; sigIdx < 1; sigIdx++) {
        switch ( 5 ) {
         case SS_DOUBLE:
          ((real_T *)sigOutputPtr)[sigIdx] = *((real_T *)(ecatRxBufPtr+bitOffset/
            8));
          break;

         case SS_SINGLE:
          ((real32_T *)sigOutputPtr)[sigIdx] = *((real32_T *)(ecatRxBufPtr+
            bitOffset/8));
          break;

         case SS_INT8:
          if ((bitOffset % 8 == 0) && (16 == 8) && (2 == sizeof(int8_T))) {
            ((int8_T *)sigOutputPtr)[sigIdx] = *((int8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT8:
          if ((bitOffset%8 == 0) && (16 == 8) && (2 == sizeof(uint8_T))) {
            ((uint8_T *)sigOutputPtr)[sigIdx] = *((uint8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_BOOLEAN:
          slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*2,
                             2);
          break;

         case SS_INT16:
          if ((bitOffset%16 == 0) && (16 == 16) && (2 == sizeof(int16_T))) {
            ((int16_T *)sigOutputPtr)[sigIdx] = *((int16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT16:
          if ((bitOffset%16 == 0) && (16 == 16) && (2 == sizeof(uint16_T))) {
            ((uint16_T *)sigOutputPtr)[sigIdx] = *((uint16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_INT32:
          if ((bitOffset%32 == 0) && (16 == 32) && (2 == sizeof(int32_T))) {
            ((int32_T *)sigOutputPtr)[sigIdx] = *((int32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         case SS_UINT32:
          if ((bitOffset%32 == 0) && (16 == 32) && (2 == sizeof(uint32_T))) {
            ((uint32_T *)sigOutputPtr)[sigIdx] = *((uint32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 16, sigOutputPtr+sigIdx*
                               2, 2);
          }
          break;

         default:
          /* Fatal error, unsupported type. This is checked in getDataSizes, so it should never happen. */
          break;
        }

        bitOffset += 16;
      }
    }

    /* DataTypeConversion: '<S7>/Data Type Conversion9' */
    MotorTorqueControlTest_workin_B.ModesofOperation =
      MotorTorqueControlTest_workin_B.EtherCATPDOReceiveCurrentValu_n;

    /* DiscreteFilter: '<S7>/2nd order, 12Hz2' */
    u = 0.0 - MotorTorqueControlTest_worki_DW.undorder12Hz2_states[0] *
      MotorTorqueControlTest_work_cal->undorder12Hz2_DenCoef[1];
    u -= MotorTorqueControlTest_worki_DW.undorder12Hz2_states[1] *
      MotorTorqueControlTest_work_cal->undorder12Hz2_DenCoef[2];
    u /= MotorTorqueControlTest_work_cal->undorder12Hz2_DenCoef[0];
    MotorTorqueControlTest_worki_DW.undorder12Hz2_tmp = u;
    u = MotorTorqueControlTest_work_cal->undorder12Hz2_NumCoef[0] *
      MotorTorqueControlTest_worki_DW.undorder12Hz2_tmp;
    u += MotorTorqueControlTest_worki_DW.undorder12Hz2_states[0] *
      MotorTorqueControlTest_work_cal->undorder12Hz2_NumCoef[1];
    u += MotorTorqueControlTest_worki_DW.undorder12Hz2_states[1] *
      MotorTorqueControlTest_work_cal->undorder12Hz2_NumCoef[2];

    /* DiscreteFilter: '<S7>/2nd order, 12Hz2' */
    MotorTorqueControlTest_workin_B.Filtered = u;

    /* DiscreteFilter: '<S7>/2nd order, 60Hz' */
    u = 0.0 - MotorTorqueControlTest_worki_DW.undorder60Hz_states[0] *
      MotorTorqueControlTest_work_cal->undorder60Hz_DenCoef[1];
    u -= MotorTorqueControlTest_worki_DW.undorder60Hz_states[1] *
      MotorTorqueControlTest_work_cal->undorder60Hz_DenCoef[2];
    u /= MotorTorqueControlTest_work_cal->undorder60Hz_DenCoef[0];
    MotorTorqueControlTest_worki_DW.undorder60Hz_tmp = u;
    u = MotorTorqueControlTest_work_cal->undorder60Hz_NumCoef[0] *
      MotorTorqueControlTest_worki_DW.undorder60Hz_tmp;
    u += MotorTorqueControlTest_worki_DW.undorder60Hz_states[0] *
      MotorTorqueControlTest_work_cal->undorder60Hz_NumCoef[1];
    u += MotorTorqueControlTest_worki_DW.undorder60Hz_states[1] *
      MotorTorqueControlTest_work_cal->undorder60Hz_NumCoef[2];

    /* DiscreteFilter: '<S7>/2nd order, 60Hz' */
    MotorTorqueControlTest_workin_B.u_60Hz = u;

    /* Switch: '<Root>/Switch4' */
    if (MotorTorqueControlTest_workin_B.ManualSwitch10 >
        MotorTorqueControlTest_work_cal->Switch4_Threshold) {
      /* Switch: '<Root>/Switch4' */
      MotorTorqueControlTest_workin_B.Switch4 =
        MotorTorqueControlTest_workin_B.EtherCATPDOReceive;
    } else {
      /* Switch: '<Root>/Switch4' incorporates:
       *  Constant: '<Root>/Constant30'
       */
      MotorTorqueControlTest_workin_B.Switch4 =
        MotorTorqueControlTest_work_cal->Constant30_Value;
    }

    /* End of Switch: '<Root>/Switch4' */

    /* RateTransition generated from: '<Root>/Motor Initliazation1' */
    rtw_slrealtime_mutex_lock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_b);
    wrBufIdx = static_cast<int8_T>
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_g + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }

    if (wrBufIdx ==
        MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_d) {
      wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
      if (wrBufIdx == 3) {
        wrBufIdx = 0;
      }
    }

    rtw_slrealtime_mutex_unlock
      (MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_b);
    switch (wrBufIdx) {
     case 0:
      MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1Inpo =
        MotorTorqueControlTest_workin_B.Switch4;
      break;

     case 1:
      MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_f =
        MotorTorqueControlTest_workin_B.Switch4;
      break;

     case 2:
      MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_e =
        MotorTorqueControlTest_workin_B.Switch4;
      break;
    }

    MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_g = wrBufIdx;

    /* End of RateTransition generated from: '<Root>/Motor Initliazation1' */
    /* user code (Output function Trailer for TID0) */
    {
      /*------------ S-Function Block: <S1>/EtherCAT Init Write Process Data ,Run Admin Tasks and then Write Acyclic Data------------*/
      xpcEtherCATWriteProcessData(0,NULL);
      xpcEtherCATExecAdminJobs(0);
      xpcEtherCATWriteAcyclicData(0);
    }
  }

  /* Update for Atomic SubSystem: '<Root>/Triggered Subsystem6' */
  /* Update for Memory: '<S8>/Memory' incorporates:
   *  RateTransition generated from: '<S8>/Memory'
   */
  std::memcpy(&MotorTorqueControlTest_worki_DW.Memory_PreviousInput_b[0],
              &MotorTorqueControlTest_workin_B.buffer_e[0], 200U * sizeof(real_T));

  /* Update for Memory: '<S8>/Memory1' */
  MotorTorqueControlTest_worki_DW.Memory1_PreviousInput =
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionOutport2;

  /* Update for Memory: '<S8>/Memory2' incorporates:
   *  RateTransition generated from: '<S8>/Memory2'
   */
  std::memcpy(&MotorTorqueControlTest_worki_DW.Memory2_PreviousInput[0],
              &MotorTorqueControlTest_workin_B.buffer[0], 200U * sizeof(real_T));

  /* Update for Memory: '<S8>/Memory3' */
  MotorTorqueControlTest_worki_DW.Memory3_PreviousInput =
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Outport2;

  /* End of Update for SubSystem: '<Root>/Triggered Subsystem6' */

  /* Update for Memory: '<Root>/Memory' */
  MotorTorqueControlTest_worki_DW.Memory_PreviousInput =
    MotorTorqueControlTest_workin_B.y;

  /* Update for DiscreteIntegrator: '<S42>/Integrator' */
  MotorTorqueControlTest_worki_DW.Integrator_DSTATE +=
    MotorTorqueControlTest_work_cal->Integrator_gainval *
    MotorTorqueControlTest_workin_B.IProdOut;

  /* Update for DiscreteIntegrator: '<S90>/Integrator' */
  MotorTorqueControlTest_worki_DW.Integrator_DSTATE_l +=
    MotorTorqueControlTest_work_cal->Integrator_gainval_f *
    MotorTorqueControlTest_workin_B.IProdOut_l;
  MotorTorqueControlTest_worki_DW.Integrator_PrevResetState = 0;

  /* Update for DiscreteFilter: '<S7>/2nd order, 12Hz2' */
  MotorTorqueControlTest_worki_DW.undorder12Hz2_states[1] =
    MotorTorqueControlTest_worki_DW.undorder12Hz2_states[0];
  MotorTorqueControlTest_worki_DW.undorder12Hz2_states[0] =
    MotorTorqueControlTest_worki_DW.undorder12Hz2_tmp;

  /* Update for DiscreteFilter: '<S7>/2nd order, 60Hz' */
  MotorTorqueControlTest_worki_DW.undorder60Hz_states[1] =
    MotorTorqueControlTest_worki_DW.undorder60Hz_states[0];
  MotorTorqueControlTest_worki_DW.undorder60Hz_states[0] =
    MotorTorqueControlTest_worki_DW.undorder60Hz_tmp;

  /* Update absolute time */
  /* The "clockTick0" counts the number of times the code of this task has
   * been executed. The absolute time is the multiplication of "clockTick0"
   * and "Timing.stepSize0". Size of "clockTick0" ensures timer will not
   * overflow during the application lifespan selected.
   * Timer of this task consists of two 32 bit unsigned integers.
   * The two integers represent the low bits Timing.clockTick0 and the high bits
   * Timing.clockTickH0. When the low bit overflows to 0, the high bits increment.
   */
  if (!(++MotorTorqueControlTest_worki_M->Timing.clockTick0)) {
    ++MotorTorqueControlTest_worki_M->Timing.clockTickH0;
  }

  MotorTorqueControlTest_worki_M->Timing.t[0] =
    MotorTorqueControlTest_worki_M->Timing.clockTick0 *
    MotorTorqueControlTest_worki_M->Timing.stepSize0 +
    MotorTorqueControlTest_worki_M->Timing.clockTickH0 *
    MotorTorqueControlTest_worki_M->Timing.stepSize0 * 4294967296.0;

  /* Update absolute time */
  /* The "clockTick1" counts the number of times the code of this task has
   * been executed. The resolution of this integer timer is 0.001, which is the step size
   * of the task. Size of "clockTick1" ensures timer will not overflow during the
   * application lifespan selected.
   * Timer of this task consists of two 32 bit unsigned integers.
   * The two integers represent the low bits Timing.clockTick1 and the high bits
   * Timing.clockTickH1. When the low bit overflows to 0, the high bits increment.
   */
  MotorTorqueControlTest_worki_M->Timing.clockTick1++;
  if (!MotorTorqueControlTest_worki_M->Timing.clockTick1) {
    MotorTorqueControlTest_worki_M->Timing.clockTickH1++;
  }
}

/* Model step function for TID2 */
void MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step2(void) /* Sample time: [0.005s, 0.0s] */
{
  real_T tmp;
  int8_T wrBufIdx;

  /* Outputs for Atomic SubSystem: '<Root>/Triggered Subsystem6' */
  /* RateTransition: '<S8>/Rate Transition' */
  MotorTorqueControlTest_worki_DW.RateTransition_RdBufIdx = static_cast<int8_T>
    (MotorTorqueControlTest_worki_DW.RateTransition_RdBufIdx == 0);

  /* RateTransition: '<S8>/Rate Transition' */
  MotorTorqueControlTest_workin_B.RateTransition =
    MotorTorqueControlTest_worki_DW.RateTransition_Buf[MotorTorqueControlTest_worki_DW.RateTransition_RdBufIdx];

  /* RateTransition generated from: '<S8>/MATLAB Function' */
  rtw_slrealtime_mutex_lock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_d);
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_R =
    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_L;
  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_d);
  switch (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_R) {
   case 0:
    /* RateTransition generated from: '<S8>/MATLAB Function' */
    for (int32_T i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport2[i] =
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_B[i];
    }
    break;

   case 1:
    /* RateTransition generated from: '<S8>/MATLAB Function' */
    for (int32_T i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport2[i] =
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_c[i];
    }
    break;

   case 2:
    /* RateTransition generated from: '<S8>/MATLAB Function' */
    for (int32_T i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport2[i] =
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_f[i];
    }
    break;
  }

  /* End of RateTransition generated from: '<S8>/MATLAB Function' */

  /* RateTransition generated from: '<S8>/MATLAB Function' */
  rtw_slrealtime_mutex_lock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_m);
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_R =
    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_L;
  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_m);
  switch (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_R) {
   case 0:
    /* RateTransition generated from: '<S8>/MATLAB Function' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport4 =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_B;
    break;

   case 1:
    /* RateTransition generated from: '<S8>/MATLAB Function' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport4 =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_g;
    break;

   case 2:
    /* RateTransition generated from: '<S8>/MATLAB Function' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport4 =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_d;
    break;
  }

  /* End of RateTransition generated from: '<S8>/MATLAB Function' */

  /* MATLAB Function: '<S8>/MATLAB Function' incorporates:
   *  Constant: '<S8>/Constant'
   */
  MotorTorqueC_MATLABFunction(MotorTorqueControlTest_workin_B.RateTransition,
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport2,
    MotorTorqueControlTest_work_cal->Constant_Value,
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport4,
    &MotorTorqueControlTest_workin_B.sf_MATLABFunction_l);

  /* Sum: '<S8>/Sum of Elements' */
  tmp = -0.0;
  for (int32_T i = 0; i < 200; i++) {
    tmp += MotorTorqueControlTest_workin_B.sf_MATLABFunction_l.newbuf[i];
  }

  /* Sum: '<S8>/Sum of Elements' */
  MotorTorqueControlTest_workin_B.SumofElements = tmp;

  /* Gain: '<S8>/Gain' */
  MotorTorqueControlTest_workin_B.Gain =
    MotorTorqueControlTest_work_cal->Gain_Gain *
    MotorTorqueControlTest_workin_B.SumofElements;

  /* RateTransition: '<S8>/Rate Transition1' */
  MotorTorqueControlTest_worki_DW.RateTransition1_RdBufIdx = static_cast<int8_T>
    (MotorTorqueControlTest_worki_DW.RateTransition1_RdBufIdx == 0);

  /* RateTransition: '<S8>/Rate Transition1' */
  MotorTorqueControlTest_workin_B.RateTransition1 =
    MotorTorqueControlTest_worki_DW.RateTransition1_Buf[MotorTorqueControlTest_worki_DW.RateTransition1_RdBufIdx];

  /* RateTransition generated from: '<S8>/MATLAB Function1' */
  rtw_slrealtime_mutex_lock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_d);
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_ha =
    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_dg;
  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_d);
  switch (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_ha) {
   case 0:
    /* RateTransition generated from: '<S8>/MATLAB Function1' */
    for (int32_T i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport2[i] =
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport2_[i];
    }
    break;

   case 1:
    /* RateTransition generated from: '<S8>/MATLAB Function1' */
    for (int32_T i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport2[i] =
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_p[i];
    }
    break;

   case 2:
    /* RateTransition generated from: '<S8>/MATLAB Function1' */
    for (int32_T i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport2[i] =
        MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_a[i];
    }
    break;
  }

  /* End of RateTransition generated from: '<S8>/MATLAB Function1' */

  /* RateTransition generated from: '<S8>/MATLAB Function1' */
  rtw_slrealtime_mutex_lock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_n);
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_au =
    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_hu;
  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_n);
  switch (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inpor_au) {
   case 0:
    /* RateTransition generated from: '<S8>/MATLAB Function1' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport4 =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport4_;
    break;

   case 1:
    /* RateTransition generated from: '<S8>/MATLAB Function1' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport4 =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_h;
    break;

   case 2:
    /* RateTransition generated from: '<S8>/MATLAB Function1' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport4 =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_j;
    break;
  }

  /* End of RateTransition generated from: '<S8>/MATLAB Function1' */

  /* MATLAB Function: '<S8>/MATLAB Function1' incorporates:
   *  Constant: '<S8>/Constant1'
   */
  MotorTorqueC_MATLABFunction(MotorTorqueControlTest_workin_B.RateTransition1,
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport2,
    MotorTorqueControlTest_work_cal->Constant1_Value_a,
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport4,
    &MotorTorqueControlTest_workin_B.sf_MATLABFunction1);

  /* Sum: '<S8>/Sum of Elements1' */
  tmp = -0.0;
  for (int32_T i = 0; i < 200; i++) {
    tmp += MotorTorqueControlTest_workin_B.sf_MATLABFunction1.newbuf[i];
  }

  /* Sum: '<S8>/Sum of Elements1' */
  MotorTorqueControlTest_workin_B.SumofElements1 = tmp;

  /* Gain: '<S8>/Gain1' */
  MotorTorqueControlTest_workin_B.Gain1_a =
    MotorTorqueControlTest_work_cal->Gain1_Gain *
    MotorTorqueControlTest_workin_B.SumofElements1;

  /* RateTransition generated from: '<S8>/MATLAB Function1' */
  rtw_slrealtime_mutex_lock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_o);
  wrBufIdx = static_cast<int8_T>
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_l + 1);
  if (wrBufIdx == 3) {
    wrBufIdx = 0;
  }

  if (wrBufIdx ==
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_b) {
    wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }
  }

  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_o);
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outport2[wrBufIdx] =
    MotorTorqueControlTest_workin_B.sf_MATLABFunction1.last_updated_idx;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_l = wrBufIdx;

  /* End of RateTransition generated from: '<S8>/MATLAB Function1' */

  /* RateTransition generated from: '<S8>/MATLAB Function' */
  rtw_slrealtime_mutex_lock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_h);
  wrBufIdx = static_cast<int8_T>
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_g + 1);
  if (wrBufIdx == 3) {
    wrBufIdx = 0;
  }

  if (wrBufIdx ==
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_l) {
    wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }
  }

  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_h);
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport2_[wrBufIdx] =
    MotorTorqueControlTest_workin_B.sf_MATLABFunction_l.last_updated_idx;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_g = wrBufIdx;

  /* End of RateTransition generated from: '<S8>/MATLAB Function' */

  /* RateTransition generated from: '<S8>/Memory2' */
  rtw_slrealtime_mutex_lock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_d0_SEMAP);
  wrBufIdx = static_cast<int8_T>
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_LstBufWR + 1);
  if (wrBufIdx == 3) {
    wrBufIdx = 0;
  }

  if (wrBufIdx == MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_RDBuf)
  {
    wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }
  }

  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_d0_SEMAP);
  for (int32_T i = 0; i < 200; i++) {
    MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_Buf[i + wrBufIdx *
      200] = MotorTorqueControlTest_workin_B.sf_MATLABFunction1.newbuf[i];
  }

  MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_LstBufWR = wrBufIdx;

  /* End of RateTransition generated from: '<S8>/Memory2' */

  /* RateTransition generated from: '<S8>/Triggered Subsystem1' */
  rtw_slrealtime_mutex_lock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_j);
  wrBufIdx = static_cast<int8_T>
    (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_d + 1);
  if (wrBufIdx == 3) {
    wrBufIdx = 0;
  }

  if (wrBufIdx ==
      MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_e) {
    wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }
  }

  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_j);
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1Inpo[wrBufIdx] =
    MotorTorqueControlTest_workin_B.Gain1_a;
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_d = wrBufIdx;

  /* End of RateTransition generated from: '<S8>/Triggered Subsystem1' */

  /* RateTransition generated from: '<S8>/Triggered Subsystem' */
  rtw_slrealtime_mutex_lock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInp_b);
  wrBufIdx = static_cast<int8_T>
    (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInp_g + 1);
  if (wrBufIdx == 3) {
    wrBufIdx = 0;
  }

  if (wrBufIdx ==
      MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemIn_bw) {
    wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }
  }

  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInp_b);
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInpor[wrBufIdx] =
    MotorTorqueControlTest_workin_B.Gain;
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInp_g = wrBufIdx;

  /* End of RateTransition generated from: '<S8>/Triggered Subsystem' */

  /* RateTransition generated from: '<S8>/Memory' */
  rtw_slrealtime_mutex_lock(MotorTorqueControlTest_worki_DW.newbuf_d0_SEMAPHORE);
  wrBufIdx = static_cast<int8_T>(MotorTorqueControlTest_worki_DW.newbuf_LstBufWR
    + 1);
  if (wrBufIdx == 3) {
    wrBufIdx = 0;
  }

  if (wrBufIdx == MotorTorqueControlTest_worki_DW.newbuf_RDBuf) {
    wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }
  }

  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.newbuf_d0_SEMAPHORE);
  for (int32_T i = 0; i < 200; i++) {
    MotorTorqueControlTest_worki_DW.newbuf_Buf[i + wrBufIdx * 200] =
      MotorTorqueControlTest_workin_B.sf_MATLABFunction_l.newbuf[i];
  }

  MotorTorqueControlTest_worki_DW.newbuf_LstBufWR = wrBufIdx;

  /* End of RateTransition generated from: '<S8>/Memory' */
  /* End of Outputs for SubSystem: '<Root>/Triggered Subsystem6' */

  /* Update absolute time */
  /* The "clockTick2" counts the number of times the code of this task has
   * been executed. The resolution of this integer timer is 0.005, which is the step size
   * of the task. Size of "clockTick2" ensures timer will not overflow during the
   * application lifespan selected.
   * Timer of this task consists of two 32 bit unsigned integers.
   * The two integers represent the low bits Timing.clockTick2 and the high bits
   * Timing.clockTickH2. When the low bit overflows to 0, the high bits increment.
   */
  MotorTorqueControlTest_worki_M->Timing.clockTick2++;
  if (!MotorTorqueControlTest_worki_M->Timing.clockTick2) {
    MotorTorqueControlTest_worki_M->Timing.clockTickH2++;
  }
}

/* Model step function for TID3 */
void MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step3(void) /* Sample time: [0.01s, 0.0s] */
{
  real_T pressure_max;
  real_T pressure_min;
  int8_T wrBufIdx;

  /* RateTransition generated from: '<Root>/Motor Initliazation1' */
  rtw_slrealtime_mutex_lock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_b);
  MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_d =
    MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_g;
  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_b);
  switch (MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_d) {
   case 0:
    /* RateTransition generated from: '<Root>/Motor Initliazation1' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1Inpo;
    break;

   case 1:
    /* RateTransition generated from: '<Root>/Motor Initliazation1' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_f;
    break;

   case 2:
    /* RateTransition generated from: '<Root>/Motor Initliazation1' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo =
      MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_e;
    break;
  }

  /* End of RateTransition generated from: '<Root>/Motor Initliazation1' */

  /* Chart: '<Root>/Motor Initliazation1' */
  /* Gateway: Motor Initliazation1 */
  MotorTorqueControlTest_worki_DW.sfEvent = -1;

  /* During: Motor Initliazation1 */
  if (MotorTorqueControlTest_worki_DW.is_active_c25_MotorTorqueContro == 0U) {
    /* Entry: Motor Initliazation1 */
    MotorTorqueControlTest_worki_DW.is_active_c25_MotorTorqueContro = 1U;

    /* Entry Internal: Motor Initliazation1 */
    /* Transition: '<S5>:2' */
    MotorTorqueControlTest_worki_DW.is_c25_MotorTorqueControlTest_w =
      MotorTorqueControlTest_IN_inits;

    /* Entry 'inits': '<S5>:1' */
    MotorTorqueControlTest_workin_B.Motor_controlword = 0.0;
  } else {
    switch (MotorTorqueControlTest_worki_DW.is_c25_MotorTorqueControlTest_w) {
     case MotorTorqueControlTest_IN_inits:
      MotorTorqueControlTest_workin_B.Motor_controlword = 0.0;

      /* During 'inits': '<S5>:1' */
      if (MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
          1632.0) {
        /* Transition: '<S5>:5' */
        MotorTorqueControlTest_worki_DW.is_c25_MotorTorqueControlTest_w =
          MotorTorqueControlTes_IN_inits1;

        /* Entry 'inits1': '<S5>:3' */
        MotorTorqueControlTest_workin_B.Motor_controlword = 6.0;

        /* Transition: '<S5>:15' */
      } else if
          ((MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
            1576.0) ||
           (MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
            8.0)) {
        /* Transition: '<S5>:16' */
        MotorTorqueControlTest_worki_DW.is_c25_MotorTorqueControlTest_w =
          MotorTorqueControlTes_IN_inits3;

        /* Entry 'inits3': '<S5>:8' */
        MotorTorqueControlTest_workin_B.Motor_controlword = 128.0;
      }
      break;

     case MotorTorqueControlTes_IN_inits1:
      MotorTorqueControlTest_workin_B.Motor_controlword = 6.0;

      /* During 'inits1': '<S5>:3' */
      if (MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
          1569.0) {
        /* Transition: '<S5>:7' */
        MotorTorqueControlTest_worki_DW.is_c25_MotorTorqueControlTest_w =
          MotorTorqueControlTes_IN_inits2;

        /* Entry 'inits2': '<S5>:6' */
        MotorTorqueControlTest_workin_B.Motor_controlword = 15.0;

        /* Transition: '<S5>:13' */
      } else if
          ((MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
            1576.0) ||
           (MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
            8.0)) {
        /* Transition: '<S5>:16' */
        MotorTorqueControlTest_worki_DW.is_c25_MotorTorqueControlTest_w =
          MotorTorqueControlTes_IN_inits3;

        /* Entry 'inits3': '<S5>:8' */
        MotorTorqueControlTest_workin_B.Motor_controlword = 128.0;
      } else if
          ((MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
            999.0) ||
           (MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
            64.0)) {
        /* Transition: '<S5>:20' */
        MotorTorqueControlTest_worki_DW.is_c25_MotorTorqueControlTest_w =
          MotorTorqueControlTest_IN_inits;

        /* Entry 'inits': '<S5>:1' */
        MotorTorqueControlTest_workin_B.Motor_controlword = 0.0;
      }
      break;

     case MotorTorqueControlTes_IN_inits2:
      MotorTorqueControlTest_workin_B.Motor_controlword = 15.0;

      /* During 'inits2': '<S5>:6' */
      /* Transition: '<S5>:14' */
      if ((MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
           1576.0) ||
          (MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
           8.0)) {
        /* Transition: '<S5>:16' */
        MotorTorqueControlTest_worki_DW.is_c25_MotorTorqueControlTest_w =
          MotorTorqueControlTes_IN_inits3;

        /* Entry 'inits3': '<S5>:8' */
        MotorTorqueControlTest_workin_B.Motor_controlword = 128.0;
      } else if
          ((MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
            999.0) ||
           (MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
            64.0)) {
        /* Transition: '<S5>:21' */
        MotorTorqueControlTest_worki_DW.is_c25_MotorTorqueControlTest_w =
          MotorTorqueControlTest_IN_inits;

        /* Entry 'inits': '<S5>:1' */
        MotorTorqueControlTest_workin_B.Motor_controlword = 0.0;
      }
      break;

     default:
      MotorTorqueControlTest_workin_B.Motor_controlword = 128.0;

      /* During 'inits3': '<S5>:8' */
      if (MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo ==
          1632.0) {
        /* Transition: '<S5>:17' */
        MotorTorqueControlTest_worki_DW.is_c25_MotorTorqueControlTest_w =
          MotorTorqueControlTest_IN_inits;

        /* Entry 'inits': '<S5>:1' */
        MotorTorqueControlTest_workin_B.Motor_controlword = 0.0;
      }
      break;
    }
  }

  /* End of Chart: '<Root>/Motor Initliazation1' */

  /* DataTypeConversion: '<S1>/Data Type Conversion' */
  pressure_max = std::floor(MotorTorqueControlTest_workin_B.Motor_controlword);
  if (rtIsNaN(pressure_max) || rtIsInf(pressure_max)) {
    pressure_max = 0.0;
  } else {
    pressure_max = std::fmod(pressure_max, 65536.0);
  }

  /* DataTypeConversion: '<S1>/Data Type Conversion' */
  MotorTorqueControlTest_workin_B.DataTypeConversion = static_cast<uint16_T>
    (pressure_max < 0.0 ? static_cast<int32_T>(static_cast<uint16_T>(-
       static_cast<int16_T>(static_cast<uint16_T>(-pressure_max)))) :
     static_cast<int32_T>(static_cast<uint16_T>(pressure_max)));

  /* RateTransition generated from: '<S1>/EtherCAT PDO Transmit' */
  rtw_slrealtime_mutex_lock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitInpo);
  wrBufIdx = static_cast<int8_T>
    (MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitIn_a + 1);
  if (wrBufIdx == 3) {
    wrBufIdx = 0;
  }

  if (wrBufIdx ==
      MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitIn_d) {
    wrBufIdx = static_cast<int8_T>(wrBufIdx + 1);
    if (wrBufIdx == 3) {
      wrBufIdx = 0;
    }
  }

  rtw_slrealtime_mutex_unlock
    (MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitInpo);
  MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitIn_n[wrBufIdx] =
    MotorTorqueControlTest_workin_B.DataTypeConversion;
  MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitIn_a = wrBufIdx;

  /* End of RateTransition generated from: '<S1>/EtherCAT PDO Transmit' */

  /* RateTransition: '<Root>/RT' */
  MotorTorqueControlTest_workin_B.PressureInsoleRaw = 0.0;

  /* Memory: '<Root>/Memory8' */
  MotorTorqueControlTest_workin_B.Memory8 =
    MotorTorqueControlTest_worki_DW.Memory8_PreviousInput;

  /* Memory: '<Root>/Memory9' */
  MotorTorqueControlTest_workin_B.Memory9 =
    MotorTorqueControlTest_worki_DW.Memory9_PreviousInput;

  /* MATLAB Function: '<Root>/MATLAB Function4' */
  MotorTorqueControlTest_workin_B.pressure_min =
    MotorTorqueControlTest_workin_B.Memory8;
  MotorTorqueControlTest_workin_B.pressure_max =
    MotorTorqueControlTest_workin_B.Memory9;
  pressure_max = MotorTorqueControlTest_workin_B.pressure_max;
  pressure_min = MotorTorqueControlTest_workin_B.pressure_min;
  MotorTorqueControlTest_workin_B.pressure_max = pressure_max;
  MotorTorqueControlTest_workin_B.pressure_min = pressure_min;
  pressure_min = MotorTorqueControlTest_workin_B.pressure_min;
  pressure_max = MotorTorqueControlTest_workin_B.pressure_max;

  /* MATLAB Function 'MATLAB Function4': '<S4>:1' */
  if (MotorTorqueControlTest_workin_B.pressure_min > 0.0) {
    /* '<S4>:1:2' */
    /* '<S4>:1:3' */
    pressure_min = 0.0;
  }

  if (MotorTorqueControlTest_workin_B.pressure_max < 0.0) {
    /* '<S4>:1:5' */
    /* '<S4>:1:6' */
    pressure_max = 0.0;
  }

  MotorTorqueControlTest_workin_B.pressure_min = pressure_min;
  MotorTorqueControlTest_workin_B.pressure_max = pressure_max;

  /* End of MATLAB Function: '<Root>/MATLAB Function4' */

  /* Update for Memory: '<Root>/Memory8' */
  MotorTorqueControlTest_worki_DW.Memory8_PreviousInput =
    MotorTorqueControlTest_workin_B.pressure_min;

  /* Update for Memory: '<Root>/Memory9' */
  MotorTorqueControlTest_worki_DW.Memory9_PreviousInput =
    MotorTorqueControlTest_workin_B.pressure_max;

  /* Update absolute time */
  /* The "clockTick3" counts the number of times the code of this task has
   * been executed. The resolution of this integer timer is 0.01, which is the step size
   * of the task. Size of "clockTick3" ensures timer will not overflow during the
   * application lifespan selected.
   * Timer of this task consists of two 32 bit unsigned integers.
   * The two integers represent the low bits Timing.clockTick3 and the high bits
   * Timing.clockTickH3. When the low bit overflows to 0, the high bits increment.
   */
  MotorTorqueControlTest_worki_M->Timing.clockTick3++;
  if (!MotorTorqueControlTest_worki_M->Timing.clockTick3) {
    MotorTorqueControlTest_worki_M->Timing.clockTickH3++;
  }
}

/* Model initialize function */
void MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_initialize(void)
{
  /* Registration code */

  /* initialize non-finites */
  rt_InitInfAndNaN(sizeof(real_T));

  /* Set task counter limit used by the static main program */
  (MotorTorqueControlTest_worki_M)->Timing.TaskCounters.cLimit[0] = 1;
  (MotorTorqueControlTest_worki_M)->Timing.TaskCounters.cLimit[1] = 1;
  (MotorTorqueControlTest_worki_M)->Timing.TaskCounters.cLimit[2] = 5;
  (MotorTorqueControlTest_worki_M)->Timing.TaskCounters.cLimit[3] = 10;

  {
    /* Setup solver object */
    rtsiSetSimTimeStepPtr(&MotorTorqueControlTest_worki_M->solverInfo,
                          &MotorTorqueControlTest_worki_M->Timing.simTimeStep);
    rtsiSetTPtr(&MotorTorqueControlTest_worki_M->solverInfo, &rtmGetTPtr
                (MotorTorqueControlTest_worki_M));
    rtsiSetStepSizePtr(&MotorTorqueControlTest_worki_M->solverInfo,
                       &MotorTorqueControlTest_worki_M->Timing.stepSize0);
    rtsiSetErrorStatusPtr(&MotorTorqueControlTest_worki_M->solverInfo,
                          (&rtmGetErrorStatus(MotorTorqueControlTest_worki_M)));
    rtsiSetRTModelPtr(&MotorTorqueControlTest_worki_M->solverInfo,
                      MotorTorqueControlTest_worki_M);
  }

  rtsiSetSimTimeStep(&MotorTorqueControlTest_worki_M->solverInfo,
                     MAJOR_TIME_STEP);
  rtsiSetSolverName(&MotorTorqueControlTest_worki_M->solverInfo,
                    "FixedStepDiscrete");
  rtmSetTPtr(MotorTorqueControlTest_worki_M,
             &MotorTorqueControlTest_worki_M->Timing.tArray[0]);
  MotorTorqueControlTest_worki_M->Timing.stepSize0 = 0.001;

  /* block I/O */
  (void) std::memset((static_cast<void *>(&MotorTorqueControlTest_workin_B)), 0,
                     sizeof(B_MotorTorqueControlTest_work_T));

  {
    int32_T i;
    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.Memory_i[i] = 0.0;
    }

    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.Memory2[i] = 0.0;
    }

    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.buffer[i] = 0.0;
    }

    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.buffer_e[i] = 0.0;
    }

    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport2[i] = 0.0;
    }

    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport2[i] = 0.0;
    }

    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.sf_MATLABFunction1.newbuf[i] = 0.0;
    }

    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_workin_B.sf_MATLABFunction_l.newbuf[i] = 0.0;
    }

    MotorTorqueControlTest_workin_B.Gain1 = 0.0;
    MotorTorqueControlTest_workin_B.ManualSwitch11 = 0.0;
    MotorTorqueControlTest_workin_B.Memory = 0.0;
    MotorTorqueControlTest_workin_B.ActualTorque = 0.0;
    MotorTorqueControlTest_workin_B.DesiredVelocity_mRPM = 0.0;
    MotorTorqueControlTest_workin_B.Product1 = 0.0;
    MotorTorqueControlTest_workin_B.ManualSwitch1 = 0.0;
    MotorTorqueControlTest_workin_B.Feedback_signal_torque = 0.0;
    MotorTorqueControlTest_workin_B.BumperTorque = 0.0;
    MotorTorqueControlTest_workin_B.FeedbackP1 = 0.0;
    MotorTorqueControlTest_workin_B.torque_error = 0.0;
    MotorTorqueControlTest_workin_B.DeadZone1 = 0.0;
    MotorTorqueControlTest_workin_B.PProdOut = 0.0;
    MotorTorqueControlTest_workin_B.Integrator = 0.0;
    MotorTorqueControlTest_workin_B.Sum = 0.0;
    MotorTorqueControlTest_workin_B.IProdOut = 0.0;
    MotorTorqueControlTest_workin_B.DeadZone = 0.0;
    MotorTorqueControlTest_workin_B.PProdOut_k = 0.0;
    MotorTorqueControlTest_workin_B.Integrator_j = 0.0;
    MotorTorqueControlTest_workin_B.Sum_o = 0.0;
    MotorTorqueControlTest_workin_B.Saturation = 0.0;
    MotorTorqueControlTest_workin_B.IProdOut_l = 0.0;
    MotorTorqueControlTest_workin_B.SineWaveFunction = 0.0;
    MotorTorqueControlTest_workin_B.AssistiveTorque = 0.0;
    MotorTorqueControlTest_workin_B.ManualSwitch10 = 0.0;
    MotorTorqueControlTest_workin_B.Filtered = 0.0;
    MotorTorqueControlTest_workin_B.u_60Hz = 0.0;
    MotorTorqueControlTest_workin_B.Switch4 = 0.0;
    MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo = 0.0;
    MotorTorqueControlTest_workin_B.PressureInsoleRaw = 0.0;
    MotorTorqueControlTest_workin_B.Memory8 = 0.0;
    MotorTorqueControlTest_workin_B.Memory9 = 0.0;
    MotorTorqueControlTest_workin_B.Memory1 = 0.0;
    MotorTorqueControlTest_workin_B.Memory3 = 0.0;
    MotorTorqueControlTest_workin_B.TmpRTBAtTriggeredSubsystemInpor = 0.0;
    MotorTorqueControlTest_workin_B.Sum_p = 0.0;
    MotorTorqueControlTest_workin_B.TmpRTBAtTriggeredSubsystem1Inpo = 0.0;
    MotorTorqueControlTest_workin_B.Sum1 = 0.0;
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Outport2 = 0.0;
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionOutport2 = 0.0;
    MotorTorqueControlTest_workin_B.RateTransition = 0.0;
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport4 = 0.0;
    MotorTorqueControlTest_workin_B.SumofElements = 0.0;
    MotorTorqueControlTest_workin_B.Gain = 0.0;
    MotorTorqueControlTest_workin_B.RateTransition1 = 0.0;
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport4 = 0.0;
    MotorTorqueControlTest_workin_B.SumofElements1 = 0.0;
    MotorTorqueControlTest_workin_B.Gain1_a = 0.0;
    MotorTorqueControlTest_workin_B.Gain5 = 0.0;
    MotorTorqueControlTest_workin_B.Motor_controlword = 0.0;
    MotorTorqueControlTest_workin_B.pressure_min = 0.0;
    MotorTorqueControlTest_workin_B.pressure_max = 0.0;
    MotorTorqueControlTest_workin_B.tau = 0.0;
    MotorTorqueControlTest_workin_B.y = 0.0;
    MotorTorqueControlTest_workin_B.TriggeredSubsystem1.offset = 0.0;
    MotorTorqueControlTest_workin_B.TriggeredSubsystem.offset = 0.0;
    MotorTorqueControlTest_workin_B.sf_MATLABFunction1.last_updated_idx = 0.0;
    MotorTorqueControlTest_workin_B.sf_MATLABFunction_l.last_updated_idx = 0.0;
  }

  /* states (dwork) */
  (void) std::memset(static_cast<void *>(&MotorTorqueControlTest_worki_DW), 0,
                     sizeof(DW_MotorTorqueControlTest_wor_T));
  MotorTorqueControlTest_worki_DW.Integrator_DSTATE = 0.0;
  MotorTorqueControlTest_worki_DW.Integrator_DSTATE_l = 0.0;
  MotorTorqueControlTest_worki_DW.undorder12Hz2_states[0] = 0.0;
  MotorTorqueControlTest_worki_DW.undorder12Hz2_states[1] = 0.0;
  MotorTorqueControlTest_worki_DW.undorder60Hz_states[0] = 0.0;
  MotorTorqueControlTest_worki_DW.undorder60Hz_states[1] = 0.0;
  MotorTorqueControlTest_worki_DW.Memory_PreviousInput = 0.0;
  MotorTorqueControlTest_worki_DW.undorder12Hz2_tmp = 0.0;
  MotorTorqueControlTest_worki_DW.undorder60Hz_tmp = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1Inpo = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_f = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_e = 0.0;
  MotorTorqueControlTest_worki_DW.Memory8_PreviousInput = 0.0;
  MotorTorqueControlTest_worki_DW.Memory9_PreviousInput = 0.0;

  {
    int32_T i;
    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_worki_DW.Memory_PreviousInput_b[i] = 0.0;
    }
  }

  MotorTorqueControlTest_worki_DW.Memory1_PreviousInput = 0.0;

  {
    int32_T i;
    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_worki_DW.Memory2_PreviousInput[i] = 0.0;
    }
  }

  MotorTorqueControlTest_worki_DW.Memory3_PreviousInput = 0.0;
  MotorTorqueControlTest_worki_DW.RateTransition_Buf[0] = 0.0;
  MotorTorqueControlTest_worki_DW.RateTransition_Buf[1] = 0.0;
  MotorTorqueControlTest_worki_DW.RateTransition1_Buf[0] = 0.0;
  MotorTorqueControlTest_worki_DW.RateTransition1_Buf[1] = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInpor[0] = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInpor[1] = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInpor[2] = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1Inpo[0] = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1Inpo[1] = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1Inpo[2] = 0.0;

  {
    int32_T i;
    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport2_[i] = 0.0;
    }
  }

  {
    int32_T i;
    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_p[i] = 0.0;
    }
  }

  {
    int32_T i;
    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_a[i] = 0.0;
    }
  }

  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport4_ = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_h = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_j = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outport2[0] = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outport2[1] = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outport2[2] = 0.0;

  {
    int32_T i;
    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_B[i] = 0.0;
    }
  }

  {
    int32_T i;
    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_c[i] = 0.0;
    }
  }

  {
    int32_T i;
    for (i = 0; i < 200; i++) {
      MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_f[i] = 0.0;
    }
  }

  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_B = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_g = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_d = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport2_[0] = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport2_[1] = 0.0;
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport2_[2] = 0.0;

  {
    int32_T i;
    for (i = 0; i < 600; i++) {
      MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_Buf[i] = 0.0;
    }
  }

  {
    int32_T i;
    for (i = 0; i < 600; i++) {
      MotorTorqueControlTest_worki_DW.newbuf_Buf[i] = 0.0;
    }
  }

  MotorTorqueControlTest_worki_DW.EtherCATInit_RWORK.EXECRATIO = 0.0;

  /* Start for Atomic SubSystem: '<Root>/Triggered Subsystem6' */
  /* Start for RateTransition generated from: '<S8>/Triggered Subsystem' */
  MotorTorqueControlTest_workin_B.TmpRTBAtTriggeredSubsystemInpor =
    MotorTorqueControlTest_work_cal->TmpRTBAtTriggeredSubsystemInpor;

  /* Start for RateTransition generated from: '<S8>/Triggered Subsystem' */
  rtw_slrealtime_mutex_init
    (&MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInp_b);

  /* Start for RateTransition generated from: '<S8>/Triggered Subsystem1' */
  MotorTorqueControlTest_workin_B.TmpRTBAtTriggeredSubsystem1Inpo =
    MotorTorqueControlTest_work_cal->TmpRTBAtTriggeredSubsystem1Inpo;

  /* Start for RateTransition generated from: '<S8>/Triggered Subsystem1' */
  rtw_slrealtime_mutex_init
    (&MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_j);
  for (int32_T i = 0; i < 200; i++) {
    /* Start for RateTransition generated from: '<S8>/MATLAB Function1' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport2[i] =
      MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunction1Inport2_;
  }

  /* Start for RateTransition generated from: '<S8>/MATLAB Function1' */
  rtw_slrealtime_mutex_init
    (&MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_d);

  /* Start for RateTransition generated from: '<S8>/MATLAB Function1' */
  MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Inport4 =
    MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunction1Inport4_;

  /* Start for RateTransition generated from: '<S8>/MATLAB Function1' */
  rtw_slrealtime_mutex_init
    (&MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_n);

  /* Start for RateTransition generated from: '<S8>/MATLAB Function1' */
  MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunction1Outport2 =
    MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunction1Outport2;

  /* Start for RateTransition generated from: '<S8>/MATLAB Function1' */
  rtw_slrealtime_mutex_init
    (&MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_o);
  for (int32_T i = 0; i < 200; i++) {
    /* Start for RateTransition generated from: '<S8>/MATLAB Function' */
    MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport2[i] =
      MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunctionInport2_I;
  }

  /* Start for RateTransition generated from: '<S8>/MATLAB Function' */
  rtw_slrealtime_mutex_init
    (&MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_d);

  /* Start for RateTransition generated from: '<S8>/MATLAB Function' */
  MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionInport4 =
    MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunctionInport4_I;

  /* Start for RateTransition generated from: '<S8>/MATLAB Function' */
  rtw_slrealtime_mutex_init
    (&MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_m);

  /* Start for RateTransition generated from: '<S8>/MATLAB Function' */
  MotorTorqueControlTest_workin_B.TmpRTBAtMATLABFunctionOutport2 =
    MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunctionOutport2_;

  /* Start for RateTransition generated from: '<S8>/MATLAB Function' */
  rtw_slrealtime_mutex_init
    (&MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_h);
  for (int32_T i = 0; i < 200; i++) {
    /* Start for RateTransition generated from: '<S8>/Memory2' */
    MotorTorqueControlTest_workin_B.buffer[i] =
      MotorTorqueControlTest_work_cal->TmpRTBAtMemory2Inport1_InitialC;
  }

  /* Start for RateTransition generated from: '<S8>/Memory2' */
  rtw_slrealtime_mutex_init
    (&MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_d0_SEMAP);
  for (int32_T i = 0; i < 200; i++) {
    /* Start for RateTransition generated from: '<S8>/Memory' */
    MotorTorqueControlTest_workin_B.buffer_e[i] =
      MotorTorqueControlTest_work_cal->newbuf_InitialCondition;
  }

  /* Start for RateTransition generated from: '<S8>/Memory' */
  rtw_slrealtime_mutex_init(&MotorTorqueControlTest_worki_DW.newbuf_d0_SEMAPHORE);

  /* End of Start for SubSystem: '<Root>/Triggered Subsystem6' */
  /* Start for S-Function (slecatinit): '<S1>/EtherCAT Init' */
  slrealtime::StartCallbackService::registerCB( std::bind
    ( S1_EtherCATInit_callback, nullptr ), 10 );

  /* Start for RateTransition generated from: '<S1>/EtherCAT PDO Transmit' */
  MotorTorqueControlTest_workin_B.TmpRTBAtEtherCATPDOTransmitInpo =
    MotorTorqueControlTest_work_cal->TmpRTBAtEtherCATPDOTransmitInpo;

  /* Start for RateTransition generated from: '<S1>/EtherCAT PDO Transmit' */
  rtw_slrealtime_mutex_init
    (&MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitInpo);

  /* Start for RateTransition generated from: '<Root>/Motor Initliazation1' */
  MotorTorqueControlTest_workin_B.TmpRTBAtMotorInitliazation1Inpo =
    MotorTorqueControlTest_work_cal->TmpRTBAtMotorInitliazation1Inpo;

  /* Start for RateTransition generated from: '<Root>/Motor Initliazation1' */
  rtw_slrealtime_mutex_init
    (&MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_b);
  MotorTorqueControlTest__PrevZCX.TriggeredSubsystem1.TriggeredSubsystem_Trig_ZCE
    = UNINITIALIZED_ZCSIG;
  MotorTorqueControlTest__PrevZCX.TriggeredSubsystem.TriggeredSubsystem_Trig_ZCE
    = UNINITIALIZED_ZCSIG;

  /* InitializeConditions for Memory: '<Root>/Memory' */
  MotorTorqueControlTest_worki_DW.Memory_PreviousInput =
    MotorTorqueControlTest_work_cal->Memory_InitialCondition_l;

  /* InitializeConditions for DiscreteIntegrator: '<S42>/Integrator' */
  MotorTorqueControlTest_worki_DW.Integrator_DSTATE =
    MotorTorqueControlTest_work_cal->DiscretePIDController_InitialCo;

  /* InitializeConditions for DiscreteIntegrator: '<S90>/Integrator' */
  MotorTorqueControlTest_worki_DW.Integrator_DSTATE_l =
    MotorTorqueControlTest_work_cal->PIDController_InitialConditionF;
  MotorTorqueControlTest_worki_DW.Integrator_PrevResetState = 2;

  /* InitializeConditions for RateTransition generated from: '<S1>/EtherCAT PDO Transmit' */
  MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitIn_n[0] =
    MotorTorqueControlTest_work_cal->TmpRTBAtEtherCATPDOTransmitInpo;

  /* InitializeConditions for DiscreteFilter: '<S7>/2nd order, 12Hz2' */
  MotorTorqueControlTest_worki_DW.undorder12Hz2_states[0] =
    MotorTorqueControlTest_work_cal->undorder12Hz2_InitialStates;

  /* InitializeConditions for DiscreteFilter: '<S7>/2nd order, 60Hz' */
  MotorTorqueControlTest_worki_DW.undorder60Hz_states[0] =
    MotorTorqueControlTest_work_cal->undorder60Hz_InitialStates;

  /* InitializeConditions for DiscreteFilter: '<S7>/2nd order, 12Hz2' */
  MotorTorqueControlTest_worki_DW.undorder12Hz2_states[1] =
    MotorTorqueControlTest_work_cal->undorder12Hz2_InitialStates;

  /* InitializeConditions for DiscreteFilter: '<S7>/2nd order, 60Hz' */
  MotorTorqueControlTest_worki_DW.undorder60Hz_states[1] =
    MotorTorqueControlTest_work_cal->undorder60Hz_InitialStates;

  /* InitializeConditions for RateTransition generated from: '<Root>/Motor Initliazation1' */
  MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1Inpo =
    MotorTorqueControlTest_work_cal->TmpRTBAtMotorInitliazation1Inpo;

  /* InitializeConditions for Memory: '<Root>/Memory8' */
  MotorTorqueControlTest_worki_DW.Memory8_PreviousInput =
    MotorTorqueControlTest_work_cal->Memory8_InitialCondition;

  /* InitializeConditions for Memory: '<Root>/Memory9' */
  MotorTorqueControlTest_worki_DW.Memory9_PreviousInput =
    MotorTorqueControlTest_work_cal->Memory9_InitialCondition;

  /* SystemInitialize for Atomic SubSystem: '<Root>/Triggered Subsystem6' */
  /* InitializeConditions for Memory: '<S8>/Memory1' */
  MotorTorqueControlTest_worki_DW.Memory1_PreviousInput =
    MotorTorqueControlTest_work_cal->Memory1_InitialCondition;

  /* InitializeConditions for Memory: '<S8>/Memory' */
  std::memcpy(&MotorTorqueControlTest_worki_DW.Memory_PreviousInput_b[0],
              &MotorTorqueControlTest_work_cal->Memory_InitialCondition[0], 200U
              * sizeof(real_T));

  /* InitializeConditions for Memory: '<S8>/Memory2' */
  std::memcpy(&MotorTorqueControlTest_worki_DW.Memory2_PreviousInput[0],
              &MotorTorqueControlTest_work_cal->Memory2_InitialCondition[0],
              200U * sizeof(real_T));

  /* InitializeConditions for Memory: '<S8>/Memory3' */
  MotorTorqueControlTest_worki_DW.Memory3_PreviousInput =
    MotorTorqueControlTest_work_cal->Memory3_InitialCondition;

  /* InitializeConditions for RateTransition: '<S8>/Rate Transition' */
  MotorTorqueControlTest_worki_DW.RateTransition_Buf[0] =
    MotorTorqueControlTest_work_cal->RateTransition_InitialCondition;
  MotorTorqueControlTest_worki_DW.RateTransition_WrBufIdx = 0;
  MotorTorqueControlTest_worki_DW.RateTransition_RdBufIdx = 1;

  /* InitializeConditions for RateTransition: '<S8>/Rate Transition1' */
  MotorTorqueControlTest_worki_DW.RateTransition1_Buf[0] =
    MotorTorqueControlTest_work_cal->RateTransition1_InitialConditio;
  MotorTorqueControlTest_worki_DW.RateTransition1_WrBufIdx = 0;
  MotorTorqueControlTest_worki_DW.RateTransition1_RdBufIdx = 1;

  /* InitializeConditions for RateTransition generated from: '<S8>/Triggered Subsystem' */
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInpor[0] =
    MotorTorqueControlTest_work_cal->TmpRTBAtTriggeredSubsystemInpor;

  /* InitializeConditions for RateTransition generated from: '<S8>/Triggered Subsystem1' */
  MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1Inpo[0] =
    MotorTorqueControlTest_work_cal->TmpRTBAtTriggeredSubsystem1Inpo;

  /* InitializeConditions for RateTransition generated from: '<S8>/MATLAB Function1' */
  for (int32_T i = 0; i < 200; i++) {
    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport2_[i] =
      MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunction1Inport2_;
  }

  /* End of InitializeConditions for RateTransition generated from: '<S8>/MATLAB Function1' */

  /* InitializeConditions for RateTransition generated from: '<S8>/MATLAB Function1' */
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport4_ =
    MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunction1Inport4_;

  /* InitializeConditions for RateTransition generated from: '<S8>/MATLAB Function1' */
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outport2[0] =
    MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunction1Outport2;

  /* InitializeConditions for RateTransition generated from: '<S8>/MATLAB Function' */
  for (int32_T i = 0; i < 200; i++) {
    MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_B[i] =
      MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunctionInport2_I;
  }

  /* End of InitializeConditions for RateTransition generated from: '<S8>/MATLAB Function' */

  /* InitializeConditions for RateTransition generated from: '<S8>/MATLAB Function' */
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_B =
    MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunctionInport4_I;

  /* InitializeConditions for RateTransition generated from: '<S8>/MATLAB Function' */
  MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport2_[0] =
    MotorTorqueControlTest_work_cal->TmpRTBAtMATLABFunctionOutport2_;

  /* InitializeConditions for RateTransition generated from: '<S8>/Memory2' */
  for (int32_T i = 0; i < 200; i++) {
    MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_Buf[i] =
      MotorTorqueControlTest_work_cal->TmpRTBAtMemory2Inport1_InitialC;
  }

  /* End of InitializeConditions for RateTransition generated from: '<S8>/Memory2' */

  /* InitializeConditions for RateTransition generated from: '<S8>/Memory' */
  for (int32_T i = 0; i < 200; i++) {
    MotorTorqueControlTest_worki_DW.newbuf_Buf[i] =
      MotorTorqueControlTest_work_cal->newbuf_InitialCondition;
  }

  /* End of InitializeConditions for RateTransition generated from: '<S8>/Memory' */
  /* End of SystemInitialize for SubSystem: '<Root>/Triggered Subsystem6' */

  /* SystemInitialize for Chart: '<Root>/Motor Initliazation1' */
  MotorTorqueControlTest_worki_DW.sfEvent = -1;
  MotorTorqueControlTest_worki_DW.is_active_c25_MotorTorqueContro = 0U;
  MotorTorqueControlTest_worki_DW.is_c25_MotorTorqueControlTest_w =
    MotorTorqueC_IN_NO_ACTIVE_CHILD;
  MotorTorqueControlTest_workin_B.Motor_controlword = 0.0;
}

/* Model terminate function */
void MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_terminate(void)
{
  /* Terminate for Atomic SubSystem: '<Root>/Triggered Subsystem6' */
  /* Terminate for RateTransition generated from: '<S8>/Triggered Subsystem' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystemInp_b);

  /* Terminate for RateTransition generated from: '<S8>/Triggered Subsystem1' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.TmpRTBAtTriggeredSubsystem1In_j);

  /* Terminate for RateTransition generated from: '<S8>/MATLAB Function1' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_d);

  /* Terminate for RateTransition generated from: '<S8>/MATLAB Function1' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Inport_n);

  /* Terminate for RateTransition generated from: '<S8>/MATLAB Function1' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunction1Outpor_o);

  /* Terminate for RateTransition generated from: '<S8>/MATLAB Function' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport2_d);

  /* Terminate for RateTransition generated from: '<S8>/MATLAB Function' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionInport4_m);

  /* Terminate for RateTransition generated from: '<S8>/MATLAB Function' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMATLABFunctionOutport_h);

  /* Terminate for RateTransition generated from: '<S8>/Memory2' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMemory2Inport1_d0_SEMAP);

  /* Terminate for RateTransition generated from: '<S8>/Memory' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.newbuf_d0_SEMAPHORE);

  /* End of Terminate for SubSystem: '<Root>/Triggered Subsystem6' */
  /* Terminate for RateTransition generated from: '<S1>/EtherCAT PDO Transmit' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.TmpRTBAtEtherCATPDOTransmitInpo);

  /* Terminate for RateTransition generated from: '<Root>/Motor Initliazation1' */
  rtw_slrealtime_mutex_destroy
    (MotorTorqueControlTest_worki_DW.TmpRTBAtMotorInitliazation1In_b);

  /* user code (Terminate function Trailer) */

  /*------------ S-Function Block: <S1>/EtherCAT Init Process Shutdown Network ------------*/
  {
    int_T status;
    status = xpcEtherCATstop(0, 1000 );/* 1 second timeout */
  }
}
