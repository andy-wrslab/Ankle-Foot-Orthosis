/* Main generated for Simulink Real-Time model MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo */
#include <ModelInfo.hpp>
#include <utilities.hpp>
#include "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo.h"
#include "rte_MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_parameters.h"

/* Task descriptors */
slrealtime::TaskInfo task_1( 0u, std::bind(MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step0), slrealtime::TaskInfo::PERIODIC, 0.001, 0, 40);
slrealtime::TaskInfo task_2( 1u, std::bind(MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step2), slrealtime::TaskInfo::PERIODIC, 0.005, 0, 39);
slrealtime::TaskInfo task_3( 2u, std::bind(MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_step3), slrealtime::TaskInfo::PERIODIC, 0.01, 0, 38);

/* Executable base address for XCP */
#ifdef __linux__
extern char __executable_start;
static uintptr_t const base_address = reinterpret_cast<uintptr_t>(&__executable_start);
#else
/* Set 0 as placeholder, to be parsed later from /proc filesystem */
static uintptr_t const base_address = 0;
#endif

/* Model descriptor */
slrealtime::ModelInfo MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_Info =
{
    "MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo",
    MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_initialize,
    MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_terminate,
    []()->char const*& { return MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_M->errorStatus; },
    []()->unsigned char& { return MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_M->Timing.stopRequestedFlag; },
    { task_1, task_2, task_3 },
    slrealtime::getSegmentVector()
};

int main(int argc, char *argv[]) {
    slrealtime::BaseAddress::set(base_address);
    return slrealtime::runModel(argc, argv, MotorTorqueControlTest_working_5_8_2022_ADC_FILT_Mo_Info);
}
