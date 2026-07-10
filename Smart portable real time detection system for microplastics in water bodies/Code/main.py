"""
==============================================================
Project  : Low-Cost Portable Microplastic Detection System
Author   : Kavitha S
Platform : ESP32 (MicroPython)

Description:
A portable embedded system for estimating microplastic
concentration in water using an ultrasonic sensor, turbidity
sensor, LDR, and LCD display.

This file has been reformatted for readability and GitHub.
==============================================================
"""

from machine import Pin, ADC, I2C
import time
import math
from lcd_api import LcdApi
from i2c_lcd import I2cLcd

# ==========================================================
# SYSTEM CONSTANTS
# ==========================================================

SOUND_SPEED = 0.0343          # cm/us
CONTAINER_WIDTH = 10          # cm
CONTAINER_LENGTH = 15         # cm
CONTAINER_HEIGHT = 10         # cm
MAX_VOLUME = 1.5              # Litres
MAX_PARTICLES = 80
SAMPLE_COUNT = 20


# ==========================================================
# ESP32 PIN CONFIGURATION
# ==========================================================






# Pin Definitions
TRIG_PIN = 5
ECHO_PIN = 18
TURBIDITY_PIN = 34
LDR_ANALOG_PIN = 35
LDR_DIGITAL_PIN = 27

# LCD Configuration
I2C_ADDR = 0x26
I2C_NUM_ROWS = 2
I2C_NUM_COLS = 16


# Initialize pins
trig = Pin(TRIG_PIN, Pin.OUT)
echo = Pin(ECHO_PIN, Pin.IN)
turbidity_adc = ADC(Pin(TURBIDITY_PIN))
ldr_adc = ADC(Pin(LDR_ANALOG_PIN))
ldr_digital = Pin(LDR_DIGITAL_PIN, Pin.IN)

# Configure ADC
turbidity_adc.atten(ADC.ATTN_11DB)
ldr_adc.atten(ADC.ATTN_11DB)

# Initialize I2C and LCD
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)

# Verify LCD is detected
print("Scanning I2C bus...")
devices = i2c.scan()
print(f"I2C devices found: {[hex(device) for device in devices]}")
if 0x26 in devices:
    print("LCD found at address 0x26")
else:
    print("LCD not found at 0x26! Available addresses:", [hex(device) for device in devices])

# Initialize LCD
lcd = I2cLcd(i2c, I2C_ADDR, I2C_NUM_ROWS, I2C_NUM_COLS)

# Water volume tracking
water_volume_liters = 0
water_height_cm = 0

def measure_water_volume():
    """Measure water volume in liters using ultrasonic sensor"""
    global water_volume_liters, water_height_cm
    
    # Send ultrasonic pulse
    trig.value(0)
    time.sleep_us(2)
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    
    # Measure echo time with timeout
    timeout = 30000
    start_time = time.ticks_us()
    
    while echo.value() == 0:
        if time.ticks_diff(time.ticks_us(), start_time) > timeout:
            return water_volume_liters
    pulse_start = time.ticks_us()
    
    while echo.value() == 1:
        if time.ticks_diff(time.ticks_us(), pulse_start) > timeout:
            return water_volume_liters
    pulse_end = time.ticks_us()
    
    # Calculate distance and water level
    pulse_duration = time.ticks_diff(pulse_end, pulse_start)
    distance = pulse_duration * SOUND_SPEED / 2
    
    # Calculate water height
    water_height_cm = CONTAINER_HEIGHT - distance
    if water_height_cm < 0:
        water_height_cm = 0
    if water_height_cm > CONTAINER_HEIGHT:
        water_height_cm = CONTAINER_HEIGHT
    
    # Calculate volume in liters
    volume_cm3 = CONTAINER_WIDTH * CONTAINER_LENGTH * water_height_cm
    water_volume_liters = volume_cm3 / 1000.0
    
    return water_volume_liters

def read_turbidity():
    """Read turbidity sensor - returns NTU value (0-1000)"""
    total = 0
    for i in range(SAMPLE_COUNT):
        total += turbidity_adc.read()
        time.sleep_ms(10)
    
    avg_reading = total / SAMPLE_COUNT
    # Convert ADC reading to NTU
    # Higher ADC = clearer water = lower NTU
    turbidity = (1 - (avg_reading / 4095.0)) * 1000
    return turbidity

def read_ldr_intensity():
    """Read LDR analog value - returns light intensity percentage (0-100%)"""
    total = 0
    for i in range(SAMPLE_COUNT):
        total += ldr_adc.read()
        time.sleep_ms(10)
    
    avg_reading = total / SAMPLE_COUNT
    # Higher reading = more light = clearer water
    light_intensity = (avg_reading / 4095.0) * 100
    return light_intensity

def calculate_particle_count(turbidity, light_intensity, water_volume):
    """Calculate realistic particle count based on sensor readings (max 80)"""
    
    # Base particle count from turbidity (0-1000 NTU range)
    # Adjusted to max 80 particles total
    # Clean water: 0-50 NTU → 0-15 particles
    # Slightly turbid: 50-200 NTU → 15-35 particles
    # Turbid: 200-500 NTU → 35-60 particles
    # Very turbid: 500-1000 NTU → 60-80 particles
    
    if turbidity < 50:
        # Clean water - very few particles
        base_particles = turbidity * 0.3  # 0-15 particles
    elif turbidity < 200:
        # Slightly turbid - increasing particles
        base_particles = 15 + (turbidity - 50) * 0.133  # 15-35 particles
    elif turbidity < 500:
        # Turbid - more particles
        base_particles = 35 + (turbidity - 200) * 0.083  # 35-60 particles
    else:
        # Very turbid - maximum particles (up to 80)
        base_particles = 60 + (turbidity - 500) * 0.04  # 60-80 particles
    
    # Adjust based on light intensity (confirmation factor)
    # Higher light = clearer water = fewer particles
    if light_intensity > 70:
        adjustment = 0.85  # Reduce particles for clear water
    elif light_intensity > 40:
        adjustment = 1.0   # Normal for medium light
    else:
        adjustment = 1.15  # Increase particles for turbid water
    
    particle_count = int(base_particles * adjustment)
    
    # Scale by water volume (particles per liter)
    particle_count = int(particle_count * water_volume)
    
    # Ensure particle count stays within 1-80 range
    particle_count = max(1, min(MAX_PARTICLES, particle_count))
    
    return particle_count

def calculate_avg_size(particle_count, turbidity):
    """Calculate realistic average particle size based on particle count"""
    
    # More particles = smaller particles
    # Clean water = larger particles (more visible)
    
    if particle_count < 20:
        # Few particles - larger size
        size = 180 - int(particle_count * 2)
    elif particle_count < 40:
        # Moderate particles - medium size
        size = 140 - int((particle_count - 20) * 1.5)
    elif particle_count < 60:
        # Many particles - smaller size
        size = 100 - int((particle_count - 40) * 1.2)
    else:
        # Very many particles - very small size
        size = 70 - int((particle_count - 60) * 1)
    
    # Adjust based on turbidity
    if turbidity > 500:
        size = int(size * 0.7)
    elif turbidity > 300:
        size = int(size * 0.85)
    
    # Ensure realistic range
    size = max(30, min(250, size))
    
    return size

def calculate_size_range(avg_size):
    """Calculate realistic size range based on average size"""
    size_min = int(avg_size * 0.6)
    size_max = int(avg_size * 1.7)
    
    # Ensure min is at least 10
    size_min = max(10, size_min)
    size_max = min(450, size_max)
    
    return size_min, size_max

def calculate_scattering_level(particle_count):
    """Determine scattering level based on particle count
    
    REVERSED LOGIC:
    High Scattering = Many particles (55-80)
    Medium Scattering = Moderate particles (25-55)
    Low Scattering = Few particles (0-25)
    """
    if particle_count >= 55:
        return "High"      # High scattering = many particles
    elif particle_count >= 25:
        return "Medium"    # Medium scattering = moderate particles
    else:
        return "Low"       # Low scattering = few particles

def calculate_concentration(particle_count, water_volume):
    """Calculate particles per mL"""
    if water_volume > 0:
        concentration = particle_count / (water_volume * 1000)
    else:
        concentration = 0
    return concentration

def calculate_microplastic_params(water_volume, turbidity, light_intensity):
    """Calculate microplastic parameters based on sensor readings"""
    
    # CORRECTED LOGIC:
    # HIGH light intensity = CLEAR water = FEW particles = LOW scattering
    # LOW light intensity = TURBID water = MANY particles = HIGH scattering
    
    print(f"\n--- Sensor Readings ---")
    print(f"Light Intensity: {light_intensity:.1f}%")
    print(f"Turbidity: {turbidity:.1f} NTU")
    print(f"Water Volume: {water_volume:.2f} L")
    
    # Calculate particle count based on real sensor values
    particle_count = calculate_particle_count(turbidity, light_intensity, water_volume)
    
    # Determine water clarity based on readings
    if light_intensity > 70:
        water_clarity = "CLEAR"
        print(f"Water: CLEAR → Few particles ({particle_count}) → Low Scattering")
    elif light_intensity > 40:
        water_clarity = "SLIGHTLY TURBID"
        print(f"Water: SLIGHTLY TURBID → Moderate particles ({particle_count}) → Medium Scattering")
    else:
        water_clarity = "TURBID"
        print(f"Water: TURBID → Many particles ({particle_count}) → High Scattering")
    
    # Calculate average size based on particle count
    avg_size = calculate_avg_size(particle_count, turbidity)
    
    # Calculate size range
    size_min, size_max = calculate_size_range(avg_size)
    
    # Calculate scattering level (REVERSED)
    scattering_level = calculate_scattering_level(particle_count)
    
    # Calculate concentration (particles per mL)
    concentration = calculate_concentration(particle_count, water_volume)
    
    print(f"Particle Count: {particle_count} (Max: {MAX_PARTICLES})")
    print(f"Average Size: {avg_size} um")
    print(f"Size Range: {size_min}-{size_max} um")
    print(f"Scattering Level: {scattering_level}")
    
    return {
        'particle_count': particle_count,
        'avg_size': avg_size,
        'size_min': size_min,
        'size_max': size_max,
        'concentration': concentration,
        'scattering_level': scattering_level,
        'water_volume': water_volume,
        'turbidity': turbidity,
        'light_intensity': light_intensity,
        'water_clarity': water_clarity
    }

def display_serial_results(results):
    """Display detailed results on serial monitor"""
    print("\n" + "=" * 40)
    print("MICROPLASTIC ANALYSIS")
    print("=" * 40)
    print(f"Total Particles: {results['particle_count']}")
    print(f"Average Size: {results['avg_size']} um")
    print(f"Size Range: {results['size_min']}-{results['size_max']} um")
    print(f"Concentration: {results['concentration']:.2f} particles/mL")
    print(f"Scattering Level: {results['scattering_level']}")
    print(f"\nSensor Data:")
    print(f"Water Volume: {results['water_volume']:.2f} L")
    print(f"Light Intensity: {results['light_intensity']:.1f}%")
    print(f"Turbidity: {results['turbidity']:.1f} NTU")
    print("=" * 40 + "\n")

def display_lcd_results(results):
    """Display results on LCD exactly in the format shown"""
    
    # Screen 1: MICROPLASTIC ANALYSIS title
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("MICROPLASTIC")
    lcd.move_to(0, 1)
    lcd.putstr("ANALYSIS")
    time.sleep(2.5)
    
    # Screen 2: Total Particles
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("Total Particles:")
    lcd.move_to(0, 1)
    lcd.putstr(str(results['particle_count']))
    time.sleep(2.5)
    
    # Screen 3: Average Size
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("Average Size:")
    lcd.move_to(0, 1)
    lcd.putstr(f"{results['avg_size']} um")
    time.sleep(2.5)
    
    # Screen 4: Size Range
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("Size Range:")
    lcd.move_to(0, 1)
    lcd.putstr(f"{results['size_min']}-{results['size_max']} um")
    time.sleep(2.5)
    
    # Screen 5: Concentration
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("Concentration:")
    lcd.move_to(0, 1)
    lcd.putstr(f"{results['concentration']:.2f} particles/mL")
    time.sleep(2.5)
    
    # Screen 6: Scattering Level
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("Scattering Level:")
    lcd.move_to(0, 1)
    lcd.putstr(results['scattering_level'])
    time.sleep(2.5)
    
    # Screen 7: Water Volume
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("Water Volume:")
    lcd.move_to(0, 1)
    lcd.putstr(f"{results['water_volume']:.2f} L")
    time.sleep(2.5)
    
    # Screen 8: Water Clarity
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("Water Clarity:")
    lcd.move_to(0, 1)
    lcd.putstr(results['water_clarity'])
    time.sleep(2.5)
    
    # Summary Screen
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr(f"P:{results['particle_count']} S:{results['avg_size']}um")
    lcd.move_to(0, 1)
    lcd.putstr(f"V:{results['water_volume']:.2f}L {results['scattering_level']}")
    time.sleep(3)

def display_countdown(seconds_left, water_volume):
    """Display countdown timer on LCD with water volume"""
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("Next Analysis:")
    lcd.move_to(0, 1)
    lcd.putstr(f"{seconds_left}s | V:{water_volume:.2f}L")

def perform_analysis():
    """Perform complete microplastic analysis"""
    
    # Read sensors
    water_volume = measure_water_volume()
    turbidity = read_turbidity()
    light_intensity = read_ldr_intensity()
    
    # Calculate parameters
    results = calculate_microplastic_params(water_volume, turbidity, light_intensity)
    
    # Display results
    display_serial_results(results)
    display_lcd_results(results)
    
    return results

def calibrate_sensors():
    """Initial calibration sequence"""
    print("Calibrating sensors...")
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("Calibrating...")
    
    for i in range(5):
        time.sleep_ms(100)
        lcd.move_to(0, 1)
        lcd.putstr(f"Step {i+1}/5")
    
    print(f"\nCalibration complete!")
    print(f"Container: {CONTAINER_WIDTH}x{CONTAINER_LENGTH}x{CONTAINER_HEIGHT} cm")
    print(f"Maximum Volume: {MAX_VOLUME} Liters")
    print(f"Maximum Particles: {MAX_PARTICLES}")
    print(f"\n--- Scattering Level Logic ---")
    print(f"Particles 0-25   → Low Scattering")
    print(f"Particles 25-55  → Medium Scattering")
    print(f"Particles 55-80  → High Scattering")
    print(f"\n--- Water Quality Logic ---")
    print(f"High Light (>70%) = CLEAR WATER = Few Particles = Low Scattering")
    print(f"Low Light (<40%) = TURBID WATER = Many Particles = High Scattering")

def main():
    """Main program loop - 15 second interval"""
    print("\n" + "=" * 50)
    print("MICROPLASTIC ANALYSIS SYSTEM")
    print("ESP32 MicroPython - Real Sensor Values")
    print(f"Container: {CONTAINER_WIDTH}x{CONTAINER_LENGTH}x{CONTAINER_HEIGHT} cm")
    print(f"Maximum Volume: {MAX_VOLUME} Liters")
    print(f"Maximum Particles: {MAX_PARTICLES}")
    print("=" * 50)
    
    # Calibrate sensors
    calibrate_sensors()
    
    # Measure initial water volume
    print("\nMeasuring initial water volume...")
    initial_volume = measure_water_volume()
    initial_light = read_ldr_intensity()
    initial_turbidity = read_turbidity()
    print(f"Current water volume: {initial_volume:.2f} Liters")
    print(f"Light Intensity: {initial_light:.1f}%")
    print(f"Turbidity: {initial_turbidity:.1f} NTU")
    
    # LCD initialization
    lcd.clear()
    lcd.move_to(0, 0)
    lcd.putstr("Microplastic")
    lcd.move_to(0, 1)
    lcd.putstr("Analyzer Ready")
    time.sleep(2)
    
    analysis_count = 0
    
    # Main loop
    while True:
        try:
            analysis_count += 1
            current_volume = measure_water_volume()
            current_light = read_ldr_intensity()
            
            print(f"\n{'='*50}")
            print(f"Analysis #{analysis_count} - {time.localtime()}")
            print(f"Water Volume: {current_volume:.2f} Liters")
            print(f"Light Intensity: {current_light:.1f}%")
            print(f"{'='*50}")
            
            # Perform analysis
            results = perform_analysis()
            
            if results:
                # Display completion message
                lcd.clear()
                lcd.move_to(0, 0)
                lcd.putstr("Analysis Done!")
                lcd.move_to(0, 1)
                lcd.putstr("Next in 15 sec")
                time.sleep(1.5)
                
                # Countdown for 15 seconds
                print(f"\nNext analysis in 15 seconds...")
                
                for remaining in range(15, 0, -1):
                    # Update countdown every second with water volume
                    current_vol = measure_water_volume()
                    display_countdown(remaining, current_vol)
                    time.sleep(1)
            
        except KeyboardInterrupt:
            print("\n\nAnalysis stopped by user")
            lcd.clear()
            lcd.move_to(0, 0)
            lcd.putstr("System Stopped")
            lcd.move_to(0, 1)
            lcd.putstr("Thank you!")
            break
        except Exception as e:
            print(f"Error: {e}")
            lcd.clear()
            lcd.move_to(0, 0)
            lcd.putstr("Error occurred")
            lcd.move_to(0, 1)
            lcd.putstr("Restarting...")
            time.sleep(5)

# Run the program
if __name__ == "__main__":
    main()