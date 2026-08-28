#include "native_renderer/resource_identity.h"

#include <algorithm>
#include <limits>

namespace pinyon_shift::native_renderer {
namespace {

constexpr uint64_t kFnvOffsetBasis = UINT64_C(14695981039346656037);
constexpr uint64_t kFnvPrime = UINT64_C(1099511628211);

void HashValue(uint64_t value, uint64_t& hash) {
  for (size_t byte = 0; byte < sizeof(value); ++byte) {
    hash ^= value & 0xFF;
    hash *= kFnvPrime;
    value >>= 8;
  }
}

}  // namespace

std::optional<PhysicalRange> PhysicalRange::FromGraphicsAddress(
    uint32_t graphics_address, uint32_t length) {
  if (!length) {
    return std::nullopt;
  }
  const uint32_t canonical_address = CanonicalPhysicalAddress(graphics_address);
  if (uint64_t(canonical_address) + length > kGuestPhysicalApertureSize) {
    return std::nullopt;
  }
  return PhysicalRange{canonical_address, length};
}

uint64_t PhysicalRange::end_exclusive() const {
  return uint64_t(address) + length;
}

bool PhysicalRange::Overlaps(const PhysicalRange& other) const {
  return valid() && other.valid() && address < other.end_exclusive() &&
         other.address < end_exclusive();
}

bool PhysicalRange::valid() const {
  return length && end_exclusive() <= kGuestPhysicalApertureSize;
}

PhysicalResourceTracker::PhysicalResourceTracker()
    : page_generations_(kGuestPhysicalApertureSize /
                        kGuestPhysicalPageSize) {}

ResourceFingerprint PhysicalResourceTracker::Capture(
    std::span<const PhysicalRange> ranges) const {
  const std::scoped_lock lock(mutex_);
  return CaptureLocked(ranges);
}

ResourceFingerprint PhysicalResourceTracker::Capture(
    const PhysicalRange& range) const {
  return Capture(std::span<const PhysicalRange>(&range, 1));
}

void PhysicalResourceTracker::Track(
    TrackedResourceId resource, std::span<const PhysicalRange> ranges) {
  if (ranges.empty() ||
      std::ranges::any_of(ranges,
                          [](const PhysicalRange& range) {
                            return !range.valid();
                          })) {
    return;
  }
  const std::scoped_lock lock(mutex_);
  auto existing = std::find_if(
      entries_.begin(), entries_.end(),
      [resource](const Entry& entry) { return entry.resource == resource; });
  if (existing == entries_.end()) {
    entries_.push_back({resource, {ranges.begin(), ranges.end()}});
  } else {
    existing->ranges.assign(ranges.begin(), ranges.end());
  }
}

bool PhysicalResourceTracker::Untrack(TrackedResourceId resource) {
  const std::scoped_lock lock(mutex_);
  const auto old_size = entries_.size();
  std::erase_if(entries_,
                [resource](const Entry& entry) {
                  return entry.resource == resource;
                });
  return entries_.size() != old_size;
}

std::vector<ResourceInvalidation> PhysicalResourceTracker::Invalidate(
    const PhysicalRange& written_range) {
  if (!written_range.valid()) {
    return {};
  }
  const std::scoped_lock lock(mutex_);
  uint64_t generation = next_generation_++;
  if (!next_generation_) {
    // Zero is reserved for never-invalidated content. Saturating is safer than
    // allowing an ancient cache key to become valid after a wrap.
    next_generation_ = std::numeric_limits<uint64_t>::max();
    generation = next_generation_;
  }

  const uint32_t first_page = written_range.address /
                              kGuestPhysicalPageSize;
  const uint32_t last_page =
      uint32_t((written_range.end_exclusive() - 1) /
               kGuestPhysicalPageSize);
  std::fill(page_generations_.begin() + first_page,
            page_generations_.begin() + last_page + 1, generation);

  std::vector<ResourceInvalidation> invalidations;
  for (const Entry& entry : entries_) {
    if (std::ranges::any_of(entry.ranges, [&](const PhysicalRange& range) {
          return range.Overlaps(written_range);
        })) {
      invalidations.push_back({entry.resource, generation});
    }
  }
  return invalidations;
}

ResourceFingerprint PhysicalResourceTracker::CaptureLocked(
    std::span<const PhysicalRange> ranges) const {
  ResourceFingerprint result{0, kFnvOffsetBasis};
  for (const PhysicalRange& range : ranges) {
    if (!range.valid()) {
      return {};
    }
    HashValue(range.address, result.fingerprint);
    HashValue(range.length, result.fingerprint);
    const uint32_t first_page = range.address / kGuestPhysicalPageSize;
    const uint32_t last_page =
        uint32_t((range.end_exclusive() - 1) / kGuestPhysicalPageSize);
    for (uint32_t page = first_page; page <= last_page; ++page) {
      const uint64_t page_generation = page_generations_[page];
      result.generation = std::max(result.generation, page_generation);
      HashValue(page_generation, result.fingerprint);
    }
  }
  return result;
}

}  // namespace pinyon_shift::native_renderer
