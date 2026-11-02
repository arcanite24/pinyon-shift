#include "ui/hostui/bitmap_font.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <fstream>

// stb_image's zlib decoder, built into the SDK's UI library with its PNG
// decoder.
extern "C" {
char* stbi_zlib_decode_malloc_guesssize(const char* buffer, int len, int initial_size,
                                        int* outlen);
int stbi_zlib_decode_buffer(char* obuffer, int olen, const char* ibuffer, int ilen);
}

namespace pinyon_shift::hostui {
namespace {

constexpr size_t kRecordSize = 8;
constexpr size_t kCodePoints = 0xFFFF;
constexpr int kCell = 24;
constexpr int kRowBytes = 2 * kCell;
constexpr int kBaseline = 19;
// The bitmap fonts' cap height (14 rows) matched to the vector fonts' (about
// 0.7 em): a cell row is 1/20 em.
constexpr float kRowsPerEm = 20.0f;

std::vector<uint8_t> ReadFile(const std::filesystem::path& path) {
  std::ifstream file(path, std::ios::binary);
  return file ? std::vector<uint8_t>(std::istreambuf_iterator<char>(file), {})
              : std::vector<uint8_t>();
}

}  // namespace

std::unique_ptr<BitmapFont> BitmapFont::Load(const std::filesystem::path& directory,
                                             std::string_view name) {
  const std::string base(name);
  const auto abc = ReadFile(directory / (base + ".abc"));
  auto sbm = ReadFile(directory / (base + ".sbm"));
  if (abc.size() < 8 || sbm.empty()) {
    return nullptr;
  }
  int size = 0;
  char* records = stbi_zlib_decode_malloc_guesssize(
      reinterpret_cast<const char*>(abc.data() + 5), int(abc.size() - 5),
      int(kCodePoints * kRecordSize), &size);
  if (!records) {
    return nullptr;
  }
  auto font = std::unique_ptr<BitmapFont>(new BitmapFont());
  font->records_.assign(records, records + size);
  std::free(records);
  if (font->records_.size() < kCodePoints * kRecordSize) {
    return nullptr;
  }
  font->bitmaps_ = std::move(sbm);
  font->missing_offset_ = 0;
  return font;
}

const BitmapFont::Record* BitmapFont::Find(char32_t code_point) const {
  thread_local Record record;
  if (code_point == 0 || code_point > kCodePoints) {
    return nullptr;
  }
  const uint8_t* at = records_.data() + size_t(code_point - 1) * kRecordSize;
  record.offset = uint32_t(at[0]) << 24 | uint32_t(at[1]) << 16 | uint32_t(at[2]) << 8 | at[3];
  record.left = at[5];
  record.width = at[6];
  record.right = at[7];
  if (record.offset == missing_offset_ || record.offset >= bitmaps_.size()) {
    return nullptr;
  }
  return &record;
}

bool BitmapFont::Has(char32_t code_point) const { return Find(code_point) != nullptr; }

float BitmapFont::Advance(char32_t code_point, float pixels_per_em) const {
  const Record* record = Find(code_point);
  if (!record) return 0.0f;
  const float scale = pixels_per_em / kRowsPerEm;
  // Half pixels, plus one pixel of the cell's spacing.
  return (float(record->left + record->width + record->right) * 0.5f + 1.0f) * scale;
}

GlyphBitmap BitmapFont::Rasterize(char32_t code_point, float pixels_per_em) const {
  GlyphBitmap bitmap;
  const Record* record = Find(code_point);
  if (!record) return bitmap;
  std::array<uint8_t, kRowBytes * kCell> cell{};
  if (stbi_zlib_decode_buffer(reinterpret_cast<char*>(cell.data()), int(cell.size()),
                              reinterpret_cast<const char*>(bitmaps_.data() + record->offset),
                              int(bitmaps_.size() - record->offset)) != int(cell.size())) {
    return bitmap;
  }
  // The ink's columns, so the scaled bitmap stays small.
  const int ink = std::clamp(int(std::ceil(record->width * 0.5f)) + 1, 1, kCell);
  const float scale = pixels_per_em / kRowsPerEm;
  bitmap.width = std::max(1, int(std::ceil(float(ink) * scale)));
  bitmap.height = std::max(1, int(std::ceil(float(kCell) * scale)));
  bitmap.left = int(std::lround(float(record->left) * 0.5f * scale));
  bitmap.top = -int(std::lround(float(kBaseline) * scale));
  bitmap.alpha.resize(size_t(bitmap.width) * bitmap.height);
  // Bilinear from the cell, sampled at pixel centres.
  const auto texel = [&](int x, int y) -> float {
    if (x < 0 || y < 0 || x >= ink || y >= kCell) return 0.0f;
    return float(cell[size_t(y) * kRowBytes + x]);
  };
  for (int y = 0; y < bitmap.height; ++y) {
    const float sy = (float(y) + 0.5f) / scale - 0.5f;
    const int y0 = int(std::floor(sy));
    const float fy = sy - float(y0);
    for (int x = 0; x < bitmap.width; ++x) {
      const float sx = (float(x) + 0.5f) / scale - 0.5f;
      const int x0 = int(std::floor(sx));
      const float fx = sx - float(x0);
      const float top = texel(x0, y0) * (1 - fx) + texel(x0 + 1, y0) * fx;
      const float bottom = texel(x0, y0 + 1) * (1 - fx) + texel(x0 + 1, y0 + 1) * fx;
      bitmap.alpha[size_t(y) * bitmap.width + x] =
          uint8_t(std::clamp(top * (1 - fy) + bottom * fy, 0.0f, 255.0f));
    }
  }
  return bitmap;
}

}  // namespace pinyon_shift::hostui
