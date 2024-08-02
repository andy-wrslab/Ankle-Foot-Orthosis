/*
 * untitled.cpp
 *
 * Academic License - for use in teaching, academic research, and meeting
 * course requirements at degree granting institutions only.  Not for
 * government, commercial, or other organizational use.
 *
 * Code generation for model "untitled".
 *
 * Model version              : 1.0
 * Simulink Coder version : 9.8 (R2022b) 13-May-2022
 * C++ source code generated on : Mon Jul  8 18:32:55 2024
 *
 * Target selection: slrealtime.tlc
 * Note: GRT includes extra infrastructure and instrumentation for prototyping
 * Embedded hardware selection: Intel->x86-64 (Linux 64)
 * Code generation objectives: Unspecified
 * Validation result: Not run
 */

#include "untitled.h"
#include "untitled_private.h"
#include <cstring>

/* Block signals (default storage) */
B_untitled_T untitled_B;

/* Block states (default storage) */
DW_untitled_T untitled_DW;

/* Real-time model */
RT_MODEL_untitled_T untitled_M_ = RT_MODEL_untitled_T();
RT_MODEL_untitled_T *const untitled_M = &untitled_M_;
void Root_EtherCATInit_callback(void * const ptr_rtm )
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
                        0,
                        0,
                        logfile.c_str(),
                        0.01,
                        0,
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

    rtmSetErrorStatus(untitled_M, errMsg);
    return;
  }
}

/* Model step function */
void untitled_step(void)
{
  {
    /* user code (Output function Header) */
    {
      /*------------ S-Function Block: <Root>/EtherCAT Init Process Received Frames ------------*/
      unsigned int data[6]= { 0 };

      int32_T msdata[4] = { 0 };

      xpcEtherCATReadProcessData(0,NULL);
      mwErrorGet((int_T)0,
                 &data[0], &data[1], &data[2], (int *)&data[3], &data[4], (int *)
                 &data[5]);
      memcpy(&untitled_B.EtherCATInit[0], data,6*sizeof(int32_T));
      mwErrorClear( (int_T)0 );

      // Clear all momentary triggered values
    }

    /* S-Function (slecatpdorx): '<Root>/EtherCAT PDO Receive' */
    {
      /*------------ S-Function Block: <Root>/EtherCAT PDO Receive PDO receive block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      uint8_T *sigOutputPtr = (uint8_T *)&untitled_B.EtherCATPDOReceive;
      uint8_T *ecatRxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatRxBufPtr = (uint8_T *)xpcEtherCATgetPDin( 0 );
      bitOffset = 208;
      for (sigIdx=0; sigIdx < 1; sigIdx++) {
        switch ( 0 ) {
         case SS_DOUBLE:
          ((real_T *)sigOutputPtr)[sigIdx] = *((real_T *)(ecatRxBufPtr+bitOffset/
            8));
          break;

         case SS_SINGLE:
          ((real32_T *)sigOutputPtr)[sigIdx] = *((real32_T *)(ecatRxBufPtr+
            bitOffset/8));
          break;

         case SS_INT8:
          if ((bitOffset % 8 == 0) && (64 == 8) && (8 == sizeof(int8_T))) {
            ((int8_T *)sigOutputPtr)[sigIdx] = *((int8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_UINT8:
          if ((bitOffset%8 == 0) && (64 == 8) && (8 == sizeof(uint8_T))) {
            ((uint8_T *)sigOutputPtr)[sigIdx] = *((uint8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_BOOLEAN:
          slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*8,
                             8);
          break;

         case SS_INT16:
          if ((bitOffset%16 == 0) && (64 == 16) && (8 == sizeof(int16_T))) {
            ((int16_T *)sigOutputPtr)[sigIdx] = *((int16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_UINT16:
          if ((bitOffset%16 == 0) && (64 == 16) && (8 == sizeof(uint16_T))) {
            ((uint16_T *)sigOutputPtr)[sigIdx] = *((uint16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_INT32:
          if ((bitOffset%32 == 0) && (64 == 32) && (8 == sizeof(int32_T))) {
            ((int32_T *)sigOutputPtr)[sigIdx] = *((int32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_UINT32:
          if ((bitOffset%32 == 0) && (64 == 32) && (8 == sizeof(uint32_T))) {
            ((uint32_T *)sigOutputPtr)[sigIdx] = *((uint32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         default:
          /* Fatal error, unsupported type. This is checked in getDataSizes, so it should never happen. */
          break;
        }

        bitOffset += 64;
      }
    }

    /* DataTypeConversion: '<Root>/Data Type Conversion' */
    untitled_B.acc = untitled_B.EtherCATPDOReceive;

    /* S-Function (slecatpdorx): '<Root>/EtherCAT PDO Receive1' */
    {
      /*------------ S-Function Block: <Root>/EtherCAT PDO Receive1 PDO receive block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      uint8_T *sigOutputPtr = (uint8_T *)&untitled_B.EtherCATPDOReceive1;
      uint8_T *ecatRxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatRxBufPtr = (uint8_T *)xpcEtherCATgetPDin( 0 );
      bitOffset = 272;
      for (sigIdx=0; sigIdx < 1; sigIdx++) {
        switch ( 0 ) {
         case SS_DOUBLE:
          ((real_T *)sigOutputPtr)[sigIdx] = *((real_T *)(ecatRxBufPtr+bitOffset/
            8));
          break;

         case SS_SINGLE:
          ((real32_T *)sigOutputPtr)[sigIdx] = *((real32_T *)(ecatRxBufPtr+
            bitOffset/8));
          break;

         case SS_INT8:
          if ((bitOffset % 8 == 0) && (64 == 8) && (8 == sizeof(int8_T))) {
            ((int8_T *)sigOutputPtr)[sigIdx] = *((int8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_UINT8:
          if ((bitOffset%8 == 0) && (64 == 8) && (8 == sizeof(uint8_T))) {
            ((uint8_T *)sigOutputPtr)[sigIdx] = *((uint8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_BOOLEAN:
          slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*8,
                             8);
          break;

         case SS_INT16:
          if ((bitOffset%16 == 0) && (64 == 16) && (8 == sizeof(int16_T))) {
            ((int16_T *)sigOutputPtr)[sigIdx] = *((int16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_UINT16:
          if ((bitOffset%16 == 0) && (64 == 16) && (8 == sizeof(uint16_T))) {
            ((uint16_T *)sigOutputPtr)[sigIdx] = *((uint16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_INT32:
          if ((bitOffset%32 == 0) && (64 == 32) && (8 == sizeof(int32_T))) {
            ((int32_T *)sigOutputPtr)[sigIdx] = *((int32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_UINT32:
          if ((bitOffset%32 == 0) && (64 == 32) && (8 == sizeof(uint32_T))) {
            ((uint32_T *)sigOutputPtr)[sigIdx] = *((uint32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         default:
          /* Fatal error, unsupported type. This is checked in getDataSizes, so it should never happen. */
          break;
        }

        bitOffset += 64;
      }
    }

    /* DataTypeConversion: '<Root>/Data Type Conversion1' */
    untitled_B.SV = untitled_B.EtherCATPDOReceive1;

    /* S-Function (slecatpdorx): '<Root>/EtherCAT PDO Receive2' */
    {
      /*------------ S-Function Block: <Root>/EtherCAT PDO Receive2 PDO receive block  ------------*/
      static int counter= 0;
      int_T sigIdx;
      int_T bitOffset;
      uint8_T *sigOutputPtr = (uint8_T *)&untitled_B.EtherCATPDOReceive2;
      uint8_T *ecatRxBufPtr;           // Pointer to the stack PDO rx buffer
      ecatRxBufPtr = (uint8_T *)xpcEtherCATgetPDin( 0 );
      bitOffset = 336;
      for (sigIdx=0; sigIdx < 1; sigIdx++) {
        switch ( 0 ) {
         case SS_DOUBLE:
          ((real_T *)sigOutputPtr)[sigIdx] = *((real_T *)(ecatRxBufPtr+bitOffset/
            8));
          break;

         case SS_SINGLE:
          ((real32_T *)sigOutputPtr)[sigIdx] = *((real32_T *)(ecatRxBufPtr+
            bitOffset/8));
          break;

         case SS_INT8:
          if ((bitOffset % 8 == 0) && (64 == 8) && (8 == sizeof(int8_T))) {
            ((int8_T *)sigOutputPtr)[sigIdx] = *((int8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_UINT8:
          if ((bitOffset%8 == 0) && (64 == 8) && (8 == sizeof(uint8_T))) {
            ((uint8_T *)sigOutputPtr)[sigIdx] = *((uint8_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_BOOLEAN:
          slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*8,
                             8);
          break;

         case SS_INT16:
          if ((bitOffset%16 == 0) && (64 == 16) && (8 == sizeof(int16_T))) {
            ((int16_T *)sigOutputPtr)[sigIdx] = *((int16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_UINT16:
          if ((bitOffset%16 == 0) && (64 == 16) && (8 == sizeof(uint16_T))) {
            ((uint16_T *)sigOutputPtr)[sigIdx] = *((uint16_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_INT32:
          if ((bitOffset%32 == 0) && (64 == 32) && (8 == sizeof(int32_T))) {
            ((int32_T *)sigOutputPtr)[sigIdx] = *((int32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         case SS_UINT32:
          if ((bitOffset%32 == 0) && (64 == 32) && (8 == sizeof(uint32_T))) {
            ((uint32_T *)sigOutputPtr)[sigIdx] = *((uint32_T *)(ecatRxBufPtr+
              bitOffset/8));
          } else {
            slrtEcatCopyBitsRx(ecatRxBufPtr, bitOffset, 64, sigOutputPtr+sigIdx*
                               8, 8);
          }
          break;

         default:
          /* Fatal error, unsupported type. This is checked in getDataSizes, so it should never happen. */
          break;
        }

        bitOffset += 64;
      }
    }

    /* DataTypeConversion: '<Root>/Data Type Conversion2' */
    untitled_B.SL = untitled_B.EtherCATPDOReceive2;

    /* S-Function (slecatgetstate): '<Root>/EtherCAT Get State' */
    {
      /*------------ S-Function Block: <Root>/EtherCAT Get State Get State for  ------------*/
      *&untitled_B.EtherCATGetState = xpcEtherCATgetState( 0 );
    }

    /* user code (Output function Trailer) */
    {
      /*------------ S-Function Block: <Root>/EtherCAT Init Write Process Data ,Run Admin Tasks and then Write Acyclic Data------------*/
      xpcEtherCATWriteProcessData(0,NULL);
      xpcEtherCATExecAdminJobs(0);
      xpcEtherCATWriteAcyclicData(0);
    }
  }

  /* Update absolute time for base rate */
  /* The "clockTick0" counts the number of times the code of this task has
   * been executed. The absolute time is the multiplication of "clockTick0"
   * and "Timing.stepSize0". Size of "clockTick0" ensures timer will not
   * overflow during the application lifespan selected.
   * Timer of this task consists of two 32 bit unsigned integers.
   * The two integers represent the low bits Timing.clockTick0 and the high bits
   * Timing.clockTickH0. When the low bit overflows to 0, the high bits increment.
   */
  if (!(++untitled_M->Timing.clockTick0)) {
    ++untitled_M->Timing.clockTickH0;
  }

  untitled_M->Timing.t[0] = untitled_M->Timing.clockTick0 *
    untitled_M->Timing.stepSize0 + untitled_M->Timing.clockTickH0 *
    untitled_M->Timing.stepSize0 * 4294967296.0;

  {
    /* Update absolute timer for sample time: [0.01s, 0.0s] */
    /* The "clockTick1" counts the number of times the code of this task has
     * been executed. The resolution of this integer timer is 0.01, which is the step size
     * of the task. Size of "clockTick1" ensures timer will not overflow during the
     * application lifespan selected.
     * Timer of this task consists of two 32 bit unsigned integers.
     * The two integers represent the low bits Timing.clockTick1 and the high bits
     * Timing.clockTickH1. When the low bit overflows to 0, the high bits increment.
     */
    untitled_M->Timing.clockTick1++;
    if (!untitled_M->Timing.clockTick1) {
      untitled_M->Timing.clockTickH1++;
    }
  }
}

/* Model initialize function */
void untitled_initialize(void)
{
  /* Registration code */
  {
    /* Setup solver object */
    rtsiSetSimTimeStepPtr(&untitled_M->solverInfo,
                          &untitled_M->Timing.simTimeStep);
    rtsiSetTPtr(&untitled_M->solverInfo, &rtmGetTPtr(untitled_M));
    rtsiSetStepSizePtr(&untitled_M->solverInfo, &untitled_M->Timing.stepSize0);
    rtsiSetErrorStatusPtr(&untitled_M->solverInfo, (&rtmGetErrorStatus
      (untitled_M)));
    rtsiSetRTModelPtr(&untitled_M->solverInfo, untitled_M);
  }

  rtsiSetSimTimeStep(&untitled_M->solverInfo, MAJOR_TIME_STEP);
  rtsiSetSolverName(&untitled_M->solverInfo,"FixedStepDiscrete");
  rtmSetTPtr(untitled_M, &untitled_M->Timing.tArray[0]);
  untitled_M->Timing.stepSize0 = 0.01;

  /* block I/O */
  (void) std::memset((static_cast<void *>(&untitled_B)), 0,
                     sizeof(B_untitled_T));

  /* states (dwork) */
  (void) std::memset(static_cast<void *>(&untitled_DW), 0,
                     sizeof(DW_untitled_T));

  /* Start for S-Function (slecatinit): '<Root>/EtherCAT Init' */
  slrealtime::StartCallbackService::registerCB( std::bind
    ( Root_EtherCATInit_callback, nullptr ), 10 );
}

/* Model terminate function */
void untitled_terminate(void)
{
  /* user code (Terminate function Trailer) */

  /*------------ S-Function Block: <Root>/EtherCAT Init Process Shutdown Network ------------*/
  {
    int_T status;
    status = xpcEtherCATstop(0, 1000 );/* 1 second timeout */
  }
}
