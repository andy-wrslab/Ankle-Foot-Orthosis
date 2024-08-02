/* Main generated for Simulink Real-Time model untitled */
#include <ModelInfo.hpp>
#include <utilities.hpp>
#include "untitled.h"

/* Task descriptors */
slrealtime::TaskInfo task_1( 0u, std::bind(untitled_step), slrealtime::TaskInfo::PERIODIC, 0.01, 0, 40);

/* Executable base address for XCP */
#ifdef __linux__
extern char __executable_start;
static uintptr_t const base_address = reinterpret_cast<uintptr_t>(&__executable_start);
#else
/* Set 0 as placeholder, to be parsed later from /proc filesystem */
static uintptr_t const base_address = 0;
#endif

/* Model descriptor */
slrealtime::ModelInfo untitled_Info =
{
    "untitled",
    untitled_initialize,
    untitled_terminate,
    []()->char const*& { return untitled_M->errorStatus; },
    []()->unsigned char& { return untitled_M->Timing.stopRequestedFlag; },
    { task_1 },
    slrealtime::SegmentVector()
};

int main(int argc, char *argv[]) {
    slrealtime::BaseAddress::set(base_address);
    return slrealtime::runModel(argc, argv, untitled_Info);
}
