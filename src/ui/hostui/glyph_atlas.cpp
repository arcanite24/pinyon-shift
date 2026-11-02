#include "ui/hostui/glyph_atlas.h"

#include <algorithm>
#include <bit>
#include <cmath>

namespace pinyon_shift::hostui {
namespace {

constexpr uint32_t kMaximumSize = 4096;
constexpr int kPadding = 1;

}  // namespace

std::u32string DecodeUtf8(std::string_view text) {
  std::u32string out;
  out.reserve(text.size());
  for (size_t i = 0; i < text.size();) {
    const auto lead = uint8_t(text[i]);
    size_t length = lead < 0x80 ? 1 : (lead >> 5) == 6 ? 2 : (lead >> 4) == 14 ? 3
                                  : (lead >> 3) == 30 ? 4 : 0;
    if (!length || i + length > text.size()) {
      out.push_back(U'�');
      ++i;
      continue;
    }
    char32_t code_point = length == 1 ? lead : lead & (0x7F >> length);
    bool valid = true;
    for (size_t k = 1; k < length; ++k) {
      const auto next = uint8_t(text[i + k]);
      valid = valid && (next >> 6) == 2;
      code_point = code_point << 6 | (next & 0x3F);
    }
    out.push_back(valid ? code_point : U'�');
    i += valid ? length : 1;
  }
  return out;
}

std::string EncodeUtf8(std::u32string_view text) {
  std::string out;
  out.reserve(text.size());
  for (char32_t c : text) {
    if (c < 0x80) {
      out.push_back(char(c));
    } else if (c < 0x800) {
      out.push_back(char(0xC0 | (c >> 6)));
      out.push_back(char(0x80 | (c & 0x3F)));
    } else if (c < 0x10000) {
      out.push_back(char(0xE0 | (c >> 12)));
      out.push_back(char(0x80 | ((c >> 6) & 0x3F)));
      out.push_back(char(0x80 | (c & 0x3F)));
    } else {
      out.push_back(char(0xF0 | (c >> 18)));
      out.push_back(char(0x80 | ((c >> 12) & 0x3F)));
      out.push_back(char(0x80 | ((c >> 6) & 0x3F)));
      out.push_back(char(0x80 | (c & 0x3F)));
    }
  }
  return out;
}

std::string UpperCase(std::string_view text) {
  std::u32string decoded = DecodeUtf8(text);
  for (char32_t& c : decoded) {
    if ((c >= U'a' && c <= U'z') || (c >= 0xE0 && c <= 0xFE && c != 0xF7) ||
        (c >= 0x430 && c <= 0x44F)) {
      c -= 0x20;
    } else if (c >= 0x450 && c <= 0x45F) {
      c -= 0x50;
    } else if (c == 0x131) {
      c = U'I';
    } else if (((c >= 0x100 && c <= 0x137) || (c >= 0x14A && c <= 0x177)) && (c & 1)) {
      c -= 1;  // pairs with the capital first
    } else if (((c >= 0x139 && c <= 0x148) || (c >= 0x179 && c <= 0x17E)) && !(c & 1)) {
      c -= 1;  // pairs with the capital second
    }
  }
  return EncodeUtf8(decoded);
}

GlyphAtlas::GlyphAtlas(const VectorFont& font, float pixels_per_em,
                       std::vector<const BitmapFont*> fallbacks)
    : font_(font), fallbacks_(std::move(fallbacks)), pixels_per_em_(pixels_per_em) {
  // Room for about eight glyphs per row.
  width_ = std::clamp<uint32_t>(std::bit_ceil(uint32_t(std::ceil(pixels_per_em * 8.0f))), 256,
                                kMaximumSize);
  Grow(std::bit_ceil(uint32_t(std::ceil(pixels_per_em * 1.5f)) + 2));
}

const GlyphAtlas::Entry* GlyphAtlas::Find(char32_t code_point) const {
  auto found = entries_.find(code_point);
  if (found == entries_.end()) {
    found = entries_.find(U'?');
  }
  return found == entries_.end() ? nullptr : &found->second;
}

float GlyphAtlas::Measure(std::u32string_view text) const {
  float width = 0.0f;
  for (char32_t code_point : text) {
    if (const Entry* entry = Find(code_point)) {
      width += entry->advance;
    }
  }
  return width;
}

bool GlyphAtlas::Prepare(std::u32string_view text) {
  bool changed = false;
  for (char32_t code_point : text) {
    if (!entries_.contains(code_point)) {
      changed |= Add(code_point);
    }
  }
  if (!entries_.contains(U'?')) {
    changed |= Add(U'?');
  }
  return changed;
}

bool GlyphAtlas::Add(char32_t code_point) {
  const VectorFont::Glyph* glyph = font_.Find(uint32_t(code_point));
  if (!glyph) {
    // Spaces have no mesh in these fonts; East Asian text comes from the
    // bitmap fonts; anything else falls back to '?'.
    if (code_point == U' ' || code_point == U' ') {
      entries_[code_point] = Entry{.advance = pixels_per_em_ * 0.25f};
      return false;
    }
    for (const BitmapFont* fallback : fallbacks_) {
      if (fallback->Has(code_point)) {
        return Pack(code_point, fallback->Rasterize(code_point, pixels_per_em_),
                    fallback->Advance(code_point, pixels_per_em_));
      }
    }
    return false;
  }
  return Pack(code_point, font_.Rasterize(*glyph, pixels_per_em_),
              glyph->advance * pixels_per_em_);
}

bool GlyphAtlas::Pack(char32_t code_point, const GlyphBitmap& bitmap, float advance) {
  Entry entry;
  entry.advance = advance;
  entry.width = bitmap.width;
  entry.height = bitmap.height;
  entry.left = bitmap.left;
  entry.top = bitmap.top;
  if (bitmap.width && bitmap.height) {
    if (bitmap.width + 2 * kPadding > int(width_)) {
      entries_[code_point] = Entry{.advance = entry.advance};
      return false;
    }
    if (shelf_x_ + bitmap.width + kPadding > int(width_)) {
      shelf_x_ = kPadding;
      shelf_y_ += shelf_height_ + kPadding;
      shelf_height_ = 0;
    }
    if (uint32_t(shelf_y_ + bitmap.height + kPadding) > height_) {
      Grow(uint32_t(shelf_y_ + bitmap.height + kPadding));
      if (uint32_t(shelf_y_ + bitmap.height + kPadding) > height_) {
        entries_[code_point] = Entry{.advance = entry.advance};
        return false;
      }
    }
    entry.x = shelf_x_;
    entry.y = shelf_y_;
    for (int row = 0; row < bitmap.height; ++row) {
      for (int column = 0; column < bitmap.width; ++column) {
        const size_t at = (size_t(entry.y + row) * width_ + entry.x + column) * 4;
        rgba_[at + 3] = bitmap.alpha[size_t(row) * bitmap.width + column];
      }
    }
    shelf_x_ += bitmap.width + kPadding;
    shelf_height_ = std::max(shelf_height_, bitmap.height);
  }
  entries_[code_point] = entry;
  return true;
}

void GlyphAtlas::Grow(uint32_t minimum_height) {
  uint32_t height = std::max<uint32_t>(height_, 16);
  while (height < minimum_height && height < kMaximumSize) {
    height *= 2;
  }
  height = std::min(height, kMaximumSize);
  if (height <= height_) {
    return;
  }
  std::vector<uint8_t> grown(size_t(width_) * height * 4);
  for (size_t i = 0; i < grown.size(); i += 4) {
    grown[i] = grown[i + 1] = grown[i + 2] = 255;
  }
  std::copy(rgba_.begin(), rgba_.end(), grown.begin());
  rgba_ = std::move(grown);
  height_ = height;
}

}  // namespace pinyon_shift::hostui
