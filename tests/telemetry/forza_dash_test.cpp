#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "telemetry/forza_dash.h"

using pinyon_shift::telemetry::CarSample;
using pinyon_shift::telemetry::EncodeDash;

namespace {

uint32_t U32(const uint8_t* data, size_t offset) {
  return uint32_t(data[offset]) | uint32_t(data[offset + 1]) << 8 |
         uint32_t(data[offset + 2]) << 16 | uint32_t(data[offset + 3]) << 24;
}

float F32(const uint8_t* data, size_t offset) {
  const uint32_t bits = U32(data, offset);
  float value;
  std::memcpy(&value, &bits, sizeof(value));
  return value;
}

}  // namespace

int main() {
  static_assert(pinyon_shift::telemetry::kDashPacketSize == 311);

  // No car: IsRaceOn 0 and nothing but the timestamp, as in the game's menus.
  {
    const auto packet = EncodeDash({}, 1234);
    assert(U32(packet.data(), 0) == 0);
    assert(U32(packet.data(), 4) == 1234);
    for (size_t i = 8; i < packet.size(); ++i) assert(packet[i] == 0);
  }

  // A car in third gear at 5,000 rpm and 30 m/s, with throttle, spinning the
  // rear wheels; fields at the offsets of FM7's Dash layout.
  {
    CarSample sample;
    sample.driving = true;
    sample.rpm = 5000.0f;
    sample.redline_rpm = 7200.0f;
    sample.gear = 3;
    sample.speed_mps = 30.0f;
    sample.wheel_slip = {0.1f, 0.2f, 1.5f, 1.6f};
    sample.throttle = 1.0f;
    sample.brake = 0.5f;
    const auto packet = EncodeDash(sample, 99);
    const uint8_t* p = packet.data();
    assert(U32(p, 0) == 1);
    assert(U32(p, 4) == 99);
    assert(F32(p, 8) == 7200.0f);
    assert(F32(p, 16) == 5000.0f);
    assert(F32(p, 84) == 0.1f && F32(p, 88) == 0.2f && F32(p, 92) == 1.5f && F32(p, 96) == 1.6f);
    assert(F32(p, 244) == 30.0f);
    assert(p[303] == 255);
    assert(p[304] == 128);
    assert(p[307] == 3);
  }

  // Idle RPM, wheel speeds, slip angles and the combined slip, and the
  // clutch, handbrake and steering, at FM7's offsets.
  {
    CarSample sample;
    sample.driving = true;
    sample.idle_rpm = 750.0f;
    sample.wheel_slip = {0.6f, 0.0f, 0.0f, 0.0f};
    sample.wheel_slip_angle = {0.8f, -0.5f, 0.0f, 0.0f};
    sample.wheel_speed_rad_s = {40.0f, 41.0f, 42.0f, 43.0f};
    sample.clutch = 1.0f;
    sample.handbrake = 0.25f;
    sample.steer = -1.0f;
    sample.suspension_m = {0.01f, 0.02f, 0.03f, 0.04f};
    sample.suspension_normalized = {0.25f, 0.5f, 0.75f, 1.0f};
    sample.surface_rumble = {0.3f, 0.3f, 0.3f, 0.3f};
    sample.velocity_forward_mps = 12.5f;
    auto packet = EncodeDash(sample, 0);
    const uint8_t* p = packet.data();
    assert(F32(p, 12) == 750.0f);
    assert(F32(p, 40) == 12.5f);
    assert(F32(p, 68) == 0.25f && F32(p, 80) == 1.0f);
    assert(F32(p, 148) == 0.3f && F32(p, 160) == 0.3f);
    assert(F32(p, 196) == 0.01f && F32(p, 208) == 0.04f);
    assert(F32(p, 100) == 40.0f && F32(p, 112) == 43.0f);
    assert(F32(p, 164) == 0.8f && F32(p, 168) == -0.5f);
    assert(F32(p, 180) > 0.9999f && F32(p, 180) < 1.0001f);  // |(0.6, 0.8)| = 1
    assert(F32(p, 184) == 0.5f);
    assert(p[305] == 255);
    assert(p[306] == 64);
    assert(int8_t(p[308]) == -127);
    sample.steer = 0.5f;
    packet = EncodeDash(sample, 0);
    assert(int8_t(packet[308]) == 64);
  }

  // Reverse is 0 and neutral 11, as FM7 sends them; a non-finite value is
  // sent as 0 rather than NaN.
  {
    CarSample sample;
    sample.driving = true;
    sample.gear = -1;
    sample.rpm = NAN;
    auto packet = EncodeDash(sample, 0);
    assert(packet[307] == 0);
    assert(F32(packet.data(), 16) == 0.0f);
    sample.gear = 0;
    packet = EncodeDash(sample, 0);
    assert(packet[307] == pinyon_shift::telemetry::kDashNeutralGear);
  }

  // The Horizon layout: the same fields, the dash part 12 bytes later.
  {
    CarSample sample;
    sample.driving = true;
    sample.rpm = 4000.0f;
    sample.speed_mps = 20.0f;
    sample.gear = 2;
    const auto packet = pinyon_shift::telemetry::EncodeHorizon(sample, 7);
    static_assert(pinyon_shift::telemetry::kHorizonPacketSize == 324);
    assert(U32(packet.data(), 0) == 1 && U32(packet.data(), 4) == 7);
    assert(F32(packet.data(), 16) == 4000.0f);
    assert(F32(packet.data(), 244 + 12) == 20.0f);
    assert(packet[307 + 12] == 2);
  }

  std::puts("forza_dash: all checks passed");
  return 0;
}
