#include "telemetry/forza_dash.h"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace pinyon_shift::telemetry {

namespace {

// Field offsets in the FM7 Dash layout: the 232-byte "Sled" block, then the
// dash fields.
constexpr size_t kIsRaceOn = 0;          // s32
constexpr size_t kTimestampMs = 4;       // u32
constexpr size_t kEngineMaxRpm = 8;      // f32
constexpr size_t kEngineIdleRpm = 12;    // f32
constexpr size_t kCurrentEngineRpm = 16; // f32
constexpr size_t kVelocityZ = 40;        // f32 m/s, the car's forward axis
constexpr size_t kNormalizedSuspensionTravel = 68;  // 4 x f32, 0 extended, 1 compressed
constexpr size_t kTireSlipRatio = 84;    // 4 x f32, FL FR RL RR
constexpr size_t kWheelRotationSpeed = 100;  // 4 x f32 rad/s
constexpr size_t kSurfaceRumble = 148;   // 4 x f32
constexpr size_t kTireSlipAngle = 164;   // 4 x f32
constexpr size_t kTireCombinedSlip = 180;  // 4 x f32
constexpr size_t kSuspensionTravelMeters = 196;  // 4 x f32
constexpr size_t kSpeed = 244;           // f32 m/s
constexpr size_t kAccel = 303;           // u8 0-255
constexpr size_t kBrake = 304;           // u8 0-255
constexpr size_t kClutch = 305;          // u8 0-255
constexpr size_t kHandBrake = 306;       // u8 0-255
constexpr size_t kGear = 307;            // u8
constexpr size_t kSteer = 308;           // s8 -127 left to 127 right

class Writer {
 public:
  explicit Writer(std::array<uint8_t, kDashPacketSize>& out) : out_(out) {}
  void U32(size_t offset, uint32_t value) {
    for (int i = 0; i < 4; ++i) out_[offset + i] = uint8_t(value >> (8 * i));
  }
  void F32(size_t offset, float value) {
    if (!std::isfinite(value)) value = 0.0f;
    uint32_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    U32(offset, bits);
  }
  void U8(size_t offset, uint8_t value) { out_[offset] = value; }
  void S8(size_t offset, int8_t value) { out_[offset] = uint8_t(value); }

 private:
  std::array<uint8_t, kDashPacketSize>& out_;
};

uint8_t Unit(float value) {
  if (!std::isfinite(value)) return 0;
  return uint8_t(std::lround(std::clamp(value, 0.0f, 1.0f) * 255.0f));
}

int8_t Signed(float value) {
  if (!std::isfinite(value)) return 0;
  return int8_t(std::lround(std::clamp(value, -1.0f, 1.0f) * 127.0f));
}

}  // namespace

std::array<uint8_t, kDashPacketSize> EncodeDash(const CarSample& sample, uint32_t timestamp_ms) {
  std::array<uint8_t, kDashPacketSize> packet{};
  Writer out(packet);
  out.U32(kTimestampMs, timestamp_ms);
  // Outside a car (menus, loading) the packet says so and carries no data,
  // as the game's own Data Out does.
  if (!sample.driving) return packet;
  out.U32(kIsRaceOn, 1);
  out.F32(kEngineMaxRpm, sample.redline_rpm);
  out.F32(kEngineIdleRpm, sample.idle_rpm);
  out.F32(kCurrentEngineRpm, sample.rpm);
  out.F32(kVelocityZ, sample.velocity_forward_mps);
  for (size_t wheel = 0; wheel < 4; ++wheel) {
    const float ratio = sample.wheel_slip[wheel];
    const float angle = sample.wheel_slip_angle[wheel];
    out.F32(kTireSlipRatio + 4 * wheel, ratio);
    out.F32(kWheelRotationSpeed + 4 * wheel, sample.wheel_speed_rad_s[wheel]);
    out.F32(kNormalizedSuspensionTravel + 4 * wheel, sample.suspension_normalized[wheel]);
    out.F32(kSuspensionTravelMeters + 4 * wheel, sample.suspension_m[wheel]);
    out.F32(kSurfaceRumble + 4 * wheel, sample.surface_rumble[wheel]);
    out.F32(kTireSlipAngle + 4 * wheel, angle);
    // Both slips are normalised to the tyre's peak, so their length is 1
    // where the tyre lets go in any direction, as FM7 reports it.
    out.F32(kTireCombinedSlip + 4 * wheel, std::sqrt(ratio * ratio + angle * angle));
  }
  out.F32(kSpeed, sample.speed_mps);
  out.U8(kAccel, Unit(sample.throttle));
  out.U8(kBrake, Unit(sample.brake));
  out.U8(kClutch, Unit(sample.clutch));
  out.U8(kHandBrake, Unit(sample.handbrake));
  out.S8(kSteer, Signed(sample.steer));
  out.U8(kGear, sample.gear < 0   ? uint8_t(0)
                : sample.gear == 0 ? kDashNeutralGear
                                   : uint8_t(std::min(sample.gear, 10)));
  return packet;
}

std::array<uint8_t, kHorizonPacketSize> EncodeHorizon(const CarSample& sample,
                                                      uint32_t timestamp_ms) {
  const auto dash = EncodeDash(sample, timestamp_ms);
  std::array<uint8_t, kHorizonPacketSize> packet{};
  std::copy(dash.begin(), dash.begin() + kHorizonGapOffset, packet.begin());
  std::copy(dash.begin() + kHorizonGapOffset, dash.end(), packet.begin() + kHorizonGapOffset + 12);
  return packet;
}

}  // namespace pinyon_shift::telemetry
