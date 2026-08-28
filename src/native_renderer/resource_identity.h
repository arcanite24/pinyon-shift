#pragma once

#include <cstdint>
#include <mutex>
#include <optional>
#include <span>
#include <vector>

namespace pinyon_shift::native_renderer {

constexpr uint32_t kGuestPhysicalAddressMask = 0x1FFFFFFF;
constexpr uint64_t kGuestPhysicalApertureSize = UINT64_C(0x20000000);
constexpr uint32_t kGuestPhysicalPageSize = 4096;

[[nodiscard]] constexpr uint32_t CanonicalPhysicalAddress(
    uint32_t graphics_address) {
  return graphics_address & kGuestPhysicalAddressMask;
}

// Canonical half-open byte range in the 512 MiB Xenon physical aperture.
// Graphics addresses may retain a physical-heap window in their upper bits;
// creation masks those aliases before validating the range.
struct PhysicalRange {
  uint32_t address = 0;
  uint32_t length = 0;

  static std::optional<PhysicalRange> FromGraphicsAddress(
      uint32_t graphics_address, uint32_t length);

  [[nodiscard]] uint64_t end_exclusive() const;
  [[nodiscard]] bool Overlaps(const PhysicalRange& other) const;
  [[nodiscard]] bool valid() const;

  bool operator==(const PhysicalRange&) const = default;
};

struct ResourceFingerprint {
  uint64_t generation = 0;
  uint64_t fingerprint = 0;

  bool operator==(const ResourceFingerprint&) const = default;
};

enum class BufferResourceClass : uint8_t {
  kVertex,
  kIndex,
  kInline,
};

struct BufferResourceKey {
  PhysicalRange range;
  BufferResourceClass resource_class = BufferResourceClass::kVertex;
  uint32_t descriptor_signature = 0;
  ResourceFingerprint content;

  bool operator==(const BufferResourceKey&) const = default;
};

struct TextureResourceKey {
  PhysicalRange base;
  std::optional<PhysicalRange> mips;
  uint64_t fetch_signature = 0;
  ResourceFingerprint content;

  bool operator==(const TextureResourceKey&) const = default;
};

enum class TrackedResourceClass : uint8_t {
  kBuffer,
  kTexture,
};

struct TrackedResourceId {
  TrackedResourceClass resource_class = TrackedResourceClass::kBuffer;
  uint64_t value = 0;

  bool operator==(const TrackedResourceId&) const = default;
};

struct ResourceInvalidation {
  TrackedResourceId resource;
  uint64_t generation = 0;

  bool operator==(const ResourceInvalidation&) const = default;
};

// Thread-safe generation and overlap tracker shared by future native caches.
// Invalidation only marks resources stale. Host objects remain owned by their
// cache so the cache can retire them behind its submission fence.
class PhysicalResourceTracker {
 public:
  PhysicalResourceTracker();

  [[nodiscard]] ResourceFingerprint Capture(
      std::span<const PhysicalRange> ranges) const;
  [[nodiscard]] ResourceFingerprint Capture(const PhysicalRange& range) const;

  void Track(TrackedResourceId resource,
             std::span<const PhysicalRange> ranges);
  bool Untrack(TrackedResourceId resource);

  [[nodiscard]] std::vector<ResourceInvalidation> Invalidate(
      const PhysicalRange& written_range);

 private:
  struct Entry {
    TrackedResourceId resource;
    std::vector<PhysicalRange> ranges;
  };

  [[nodiscard]] ResourceFingerprint CaptureLocked(
      std::span<const PhysicalRange> ranges) const;

  mutable std::mutex mutex_;
  std::vector<uint64_t> page_generations_;
  std::vector<Entry> entries_;
  uint64_t next_generation_ = 1;
};

}  // namespace pinyon_shift::native_renderer
