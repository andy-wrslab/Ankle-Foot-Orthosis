#include "rte_MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_parameters.h"
#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo.h"
#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_cal.h"

extern MotorTorqueControlTest_cal_type MotorTorqueControlTest_cal_impl;
namespace slrealtime
{
  /* Description of SEGMENTS */
  SegmentVector segmentInfo {
    { (void*)&MotorTorqueControlTest_cal_impl, (void**)
      &MotorTorqueControlTest_work_cal, sizeof(MotorTorqueControlTest_cal_type),
      2 }
  };

  SegmentVector &getSegmentVector(void)
  {
    return segmentInfo;
  }
}                                      // slrealtime
