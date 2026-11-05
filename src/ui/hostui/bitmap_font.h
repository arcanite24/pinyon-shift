#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>
#include <string_view>
#include <vector>

#include "ui/hostui/vector_font.h"

namespace pinyon_shift::hostui {

// The title's East Asian bitmap fonts (`media/ui/fonts/JPB`, `KORB`, `CHTB`),
// which the host UI falls back to for the characters its vector fonts lack
// (AC-2.7). `<name>.abc` holds a 5-byte header and a zlib stream of one
// 8-byte record per code point (record i is code point i + 1): a big-endian
// offset into `<name>.sbm`, then a zero byte and the left bearing, ink width
// and right bearing in half pixels. `<name>.sbm` is a run of zlib streams,
// one per glyph, each two 24x24 8-bit coverage layers side by side (rows of
// 48 bytes); the left layer is used. Glyphs sit left-aligned in the cell with
// the baseline at row 19. Code points without a glyph point at the first
// stream.
class BitmapFont {
 public:
  static std::unique_ptr<BitmapFont> Load(const std::filesystem::path& directory,
                                          std::string_view name);

  bool Has(char32_t code_point) const;
  // Advance in pixels at `pixels_per_em` of the vector font it stands in
  // for, and the glyph's coverage scaled to that size.
  float Advance(char32_t code_point, float pixels_per_em) const;
  GlyphBitmap Rasterize(char32_t code_point, float pixels_per_em) const;

 private:
  struct Record {
    uint32_t offset = 0;
    uint8_t left = 0, width = 0, right = 0;
  };
  const Record* Find(char32_t code_point) const;

  std::vector<uint8_t> records_;  // the decompressed .abc
  std::vector<uint8_t> bitmaps_;  // the .sbm as stored
  uint32_t missing_offset_ = 0;
};

}  // namespace pinyon_shift::hostui
