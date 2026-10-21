#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace pinyon_shift::telemetry {

// What the host knows about the player's car in one frame (#481): the
// fields read for DualSense effects (site/findings/objects.toml, car
// dynamics). Everything else in the packet stays zero.
struct CarSample {
  bool driving = false;  // a player car exists and the game is in control of it
  float rpm = 0.0f;
  float idle_rpm = 0.0f;
  float redline_rpm = 0.0f;
  int gear = 0;  // 0 neutral, -1 reverse, 1-8
  float speed_mps = 0.0f;
  // Longitudinal slip per wheel (FL, FR, RL, RR), 1 at the tyre's peak grip.
  std::array<float, 4> wheel_slip{};
  // Slip angle per wheel, also 1 at the tyre's peak grip.
  std::array<float, 4> wheel_slip_angle{};
  std::array<float, 4> wheel_speed_rad_s{};  // wheel rotation speed
  // Suspension compression from the spring's rest point, in metres
  // (positive compressed), and the same over the travel seen so far, 0
  // fully extended to 1 fully compressed.
  std::array<float, 4> suspension_m{};
  std::array<float, 4> suspension_normalized{};
  // The game's own rumble for bumps, kerbs and impacts (its low-frequency
  // motor, 0-1), the feel its designers gave a controller.
  std::array<float, 4> surface_rumble{};
  // Velocity along the car's forward axis (FM7's VelocityZ), m/s; negative
  // reversing.
  float velocity_forward_mps = 0.0f;
  // The car's controls after the game's own input handling (assists, the
  // automatic clutch), so a pad, a wheel and the keyboard all report here.
  float throttle = 0.0f;   // 0-1
  float brake = 0.0f;      // 0-1
  float clutch = 0.0f;     // 0-1
  float handbrake = 0.0f;  // 0-1
  float steer = 0.0f;      // -1 left to 1 right
};

// Forza Motorsport 7's "Data Out" Dash packet: 311 bytes, little endian.
// Telemetry tools (SimHub, dashboards, motion software) read this layout.
constexpr size_t kDashPacketSize = 311;
// FM7 sends neutral as 11 and reverse as 0.
constexpr uint8_t kDashNeutralGear = 11;

std::array<uint8_t, kDashPacketSize> EncodeDash(const CarSample& sample, uint32_t timestamp_ms);

// Forza Horizon 4 and 5 send the same fields with 12 more bytes between the
// Sled block and the dash fields (324 bytes); tools read that layout under
// their Forza Horizon profile.
constexpr size_t kHorizonPacketSize = 324;
constexpr size_t kHorizonGapOffset = 232;
std::array<uint8_t, kHorizonPacketSize> EncodeHorizon(const CarSample& sample,
                                                      uint32_t timestamp_ms);

}  // namespace pinyon_shift::telemetry
