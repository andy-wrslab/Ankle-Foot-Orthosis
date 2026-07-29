### IMU 250 Hz and EasyCAT Timing Adjustments

- **Goal**: Restore reliable IMU reads at 250 Hz while preventing EasyCAT from starving Serial4/IMU UART.

- **Change 1**: Stop calling `EASYCAT.MainTask()` from an interrupt.
  - **What**: Modify `sendEasyCatData_ISR()` to only set a flag and move `EASYCAT.MainTask()` to the main `loop()`.
  - **Why**: SPI transactions in `EASYCAT.MainTask()` can disable interrupts, starving the IMU UART when executed inside an ISR.
  - **Expected outcome**: IMU reads are no longer delayed by EasyCAT; 250 Hz achievable.
  - **Actual outcome**: TBD after on-device test.

- **Change 2 (reverted)**: IMU polling interval.
  - **Originally**: Set `READ_IMU_INTERVAL` to 4000 µs (4 ms) to match `sStreamingTime.interval`.
  - **Issue**: If the IMU delivers slower than 250 Hz, fixed 4 ms polling can stretch gaps to 8 ms, increasing latency.
  - **Action**: Reverted to `READ_IMU_INTERVAL = 2000` µs (2 ms) to poll more frequently and capture packets as soon as they arrive.
  - **Expected outcome**: Reduced worst-case inter-sample delay; better responsiveness to late packets.
  - **Actual outcome**: TBD after on-device test.

- **Change 3**: Run EasyCAT + application in foreground.
  - **What**: In `loop()`, when `easycat_poll_due` is set, call `application()` then `EASYCAT.MainTask()`.
  - **Why**: Allow higher-priority interrupts (e.g., Serial/UART) to preempt foreground work.
  - **Expected outcome**: Reduced interference with IMU UART.
  - **Actual outcome**: TBD after on-device test.

- **Change 4**: Remove unnecessary `noInterrupts()` around `application()` and noisy Serial prints.
  - **What**: Eliminate critical sections and debug prints that could add latency/jitter.
  - **Why**: Minimize interrupt blocking and serial overhead.
  - **Expected outcome**: Lower jitter, fewer dropped IMU packets.
  - **Actual outcome**: TBD after on-device test.

- **Notes**:
  - `sStreamingTime.interval` for the IMU remains at 4000 µs (250 Hz).
  - EasyCAT poll timer increased to 4000 µs (250 Hz) to reduce SPI load during debugging.
  - If IMU still lags, consider lowering EasyCAT rate further or batching application data.

- **Change 5 (reverted)**: Reduce IMU payload per packet.
  - **Originally**: Stream only quaternion and corrected linear acceleration.
  - **Issue**: Packet size no longer matched `structStreamingData`, so the reader waited for a larger packet and stalled updates.
  - **Action**: Restored full payload (quat + corrected linear acceleration + corrected gyro + corrected accelerometer) to match parser struct.
  - **Expected outcome**: Continuous updates and prints resume.
  - **Actual outcome**: TBD after on-device test.

- **Change 6**: Move heavy work out of ISRs to reduce UART starvation.
  - **What**: `readSensors()` and `filterSensors()` are now triggered by timer ISRs that only set flags; actual work runs in `loop()`.
  - **Why**: Long-running ISRs at 5 kHz and 1 kHz were likely preempting Serial4 RX interrupts, stretching IMU inter-sample times to ~18 ms.
  - **Also**: Set timer priorities so these flag ISRs run but with lower preemption than IMU flag ISR and Serial.
  - **Expected outcome**: IMU update deltas decrease toward ~4–8 ms; prints continue uninterrupted.
  - **Actual outcome**: TBD after on-device test.

- **Change 7**: Prioritize IMU handling and minimize print overhead.
  - **What**: Handle the IMU flag first in `loop()` before other work; reduce debug print to only `micros()` to minimize USB overhead.
  - **Why**: Reduce latency between IMU data availability and read; avoid slow serial formatting impacting timing.
  - **Expected outcome**: Deltas closer to 4 ms with fewer outliers >6–8 ms.
  - **Actual outcome**: TBD after on-device test.

- **Change 8**: Further reduce EasyCAT polling during debug.
  - **What**: Increased `EASYCAT_TIMER_INTERVAL` to 8000 µs (125 Hz) temporarily.
  - **Why**: Lower SPI transaction frequency to reduce contention with Serial4.
  - **Expected outcome**: Fewer long gaps in IMU prints; approach ~4 ms cadence.
  - **Actual outcome**: TBD after on-device test.

- **Change 9**: Optional disable of EasyCAT during timing debug.
  - **What**: Added `easycat_enabled` flag (default false). If disabled, we skip `EASYCAT.MainTask()` and do not start its timer.
  - **Why**: Allow isolating IMU timing without SPI contention.
  - **Expected outcome**: Deltas converge toward 4.0 ms with minimal outliers.
  - **Actual outcome**: TBD after on-device test.

- **Change 10**: Faster IMU bulk read.
  - **What**: Use `Serial4.readBytes(...)` to read the full IMU packet in one call when available, then copy to the union.
  - **Why**: Reduce per-byte overhead and jitter in the IMU read path.
  - **Expected outcome**: More consistent inter-sample timing, fewer >4 ms spikes.
  - **Note**: Preserve original byte-reversal when copying into `uStreamingDataIMU1.vData` to match existing struct endianness.
  - **Actual outcome**: TBD after on-device test.

- **Change 11**: Optionally disable sensors and filter timers during debug.
  - **What**: Added `sensors_enabled` and `filter_enabled` flags (default false) and only start their timers when enabled.
  - **Why**: Eliminate non-essential workload during timing verification.
  - **Expected outcome**: IMU intervals approach 4.0 ms consistently without overflow.
  - **Actual outcome**: TBD after on-device test.

- **Change 12**: Add bounded wait for full IMU packet.
  - **What**: If some bytes have arrived but not the full packet, wait up to ~800 µs for the remainder before deferring.
  - **Why**: Reduce cases where reads slip to the next 2 ms poll, causing 6–8 ms gaps.
  - **Expected outcome**: Fewer 6–8 ms outliers; more samples at exactly 4 ms.
  - **Actual outcome**: TBD after on-device test.

- **Change 13**: Read multiple IMU packets per loop when available.
  - **What**: In `loop()`, if `Serial4.available()` has a full packet (or more), call `readIMU()` repeatedly (up to 3 times) to consume all available packets.
  - **Why**: Avoid waiting for the next timer tick when data is already buffered; reduce 6–8 ms gaps.
  - **Expected outcome**: Intervals at or very near 4.0 ms consistently.
  - **Actual outcome**: TBD after on-device test.

- **Change 14**: Verify EasyCAT timing at 2 kHz.
  - **What**: Set `EASYCAT_TIMER_INTERVAL = 500` µs and enable EasyCAT. Added debug print in `loop()` that prints the sum of 10 intervals (`EC dt10(us)`) to verify ~5000 µs total.
  - **Why**: Ensure EasyCAT is scheduled at 2 kHz without relying on external device.
  - **Expected outcome**: `EC dt10(us)` prints around 5000 µs consistently.
  - **Actual outcome**: TBD after on-device test.


