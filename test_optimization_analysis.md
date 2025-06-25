# Test Schedule Control Optimization Analysis

## Current Behavior

The long 20-second waits in `test_schedule_ctrl_execute_force` and similar tests are due to:

1. **Valve control worker polling intervals**:
   - Main loop: 100ms
   - File system checks: 500ms (every 5 iterations)
   - Flow reporting: 10 seconds
   - Zero flow detection: 5 seconds (TIME_ZERO_TAIL)

2. **Test timeline**:
   - 00:00 - Test setup, schedule for 00:01
   - 00:01 - Schedule triggers, valve opens
   - 00:02 - Valve should close after 1 minute (but needs detection)
   - 00:03 - Final state verification

## Optimization Strategies

### 1. **Mock the timing constants for tests**
```python
@pytest.fixture
def fast_valve_timing(mocker):
    """Reduce valve timing constants for faster tests"""
    mocker.patch("rasp_water.valve.TIME_ZERO_TAIL", 0.5)  # 5s -> 0.5s
    mocker.patch("rasp_water.valve.TIME_CLOSE_FAIL", 5)   # 45s -> 5s
    mocker.patch("rasp_water.valve.TIME_OPEN_FAIL", 10)   # 61s -> 10s
```

### 2. **Add event-based signaling**
Instead of polling, add a mechanism to signal when valve operations complete:

```python
# In valve.py control_worker
if stop_measure:
    # Signal completion
    if hasattr(queue, '_test_completion_event'):
        queue._test_completion_event.set()
```

### 3. **Create a test-specific wait helper**
```python
def wait_for_valve_completion(client, timeout=30):
    """Wait for valve operation to complete with early exit"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = client.get(f"{my_lib.webapp.config.URL_PREFIX}/api/valve_ctrl")
        if response.json.get("state") == 0:  # IDLE
            # Check if flow measurement completed
            time.sleep(0.5)  # Small buffer
            return True
        time.sleep(0.1)
    return False
```

### 4. **Optimize the specific test waits**
Replace the fixed 20-second waits with condition-based waits:

```python
# Instead of:
time.sleep(20)

# Use:
# Wait for scheduler to process (max 1s should be enough)
time.sleep(1)  

# For valve completion, poll status instead of fixed wait
for _ in range(50):  # 5 seconds max
    if check_valve_idle():
        break
    time.sleep(0.1)
```

### 5. **Parallel test isolation**
The scheduler uses worker-specific instances already:
```python
worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
```

This ensures parallel test isolation is maintained.

## Recommended Implementation

1. **Short term**: Reduce the sleep times from 20s to 2-3s and add status polling
2. **Medium term**: Mock timing constants in tests  
3. **Long term**: Add event-based completion signaling

The tests are primarily waiting for the valve control worker to:
- Detect the valve close (up to 500ms delay)
- Accumulate zero flow readings (5 seconds)
- Report the total flow

By reducing TIME_ZERO_TAIL in tests and polling for completion, we can reduce each 20s wait to ~2-3s.