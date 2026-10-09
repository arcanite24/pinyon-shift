#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <set>
#include <string>
#include <vector>

#include "ui/hostui/fh1_archive.h"
#include "ui/hostui/glyph_atlas.h"
#include "ui/hostui/menu.h"
#include "ui/hostui/vector_font.h"
#include "ui/hostui/xds_texture.h"

using namespace pinyon_shift::hostui;

namespace {

int failures = 0;

#define CHECK(condition)                                                        \
  do {                                                                          \
    if (!(condition)) {                                                         \
      std::fprintf(stderr, "%s:%d: check failed: %s\n", __FILE__, __LINE__,   \
                   #condition);                                                 \
      ++failures;                                                               \
    }                                                                           \
  } while (false)

void PutBe16(std::vector<uint8_t>& data, size_t at, uint16_t value) {
  data[at] = uint8_t(value >> 8);
  data[at + 1] = uint8_t(value);
}

void PutBe32(std::vector<uint8_t>& data, size_t at, uint32_t value) {
  for (int i = 0; i < 4; ++i) {
    data[at + i] = uint8_t(value >> (24 - 8 * i));
  }
}

void PutLe16(std::vector<uint8_t>& data, uint16_t value) {
  data.push_back(uint8_t(value));
  data.push_back(uint8_t(value >> 8));
}

void PutLe32(std::vector<uint8_t>& data, uint32_t value) {
  for (int i = 0; i < 4; ++i) {
    data.push_back(uint8_t(value >> (8 * i)));
  }
}

// Half floats for the few exact values the tests use.
uint16_t Half(float value) {
  if (value == 0.0f) {
    return 0;
  }
  uint32_t bits;
  std::memcpy(&bits, &value, 4);
  const uint32_t sign = (bits >> 16) & 0x8000;
  const int exponent = int((bits >> 23) & 0xFF) - 127 + 15;
  return uint16_t(sign | uint32_t(exponent) << 10 | ((bits >> 13) & 0x3FF));
}

// A vfont with square glyphs: four triangles fanned from an interior centre
// (v = 1) to outline corners (v = 0), all inside (x > 0).
std::vector<uint8_t> MakeVectorFont(const std::vector<std::pair<uint32_t, float>>& glyphs,
                                    float corner_v = 0.0f) {
  const size_t base = 0x190;
  const size_t hash_size = 4;
  const size_t after_hash = 0x36C + 4 * hash_size;
  const size_t metrics = after_hash + 8;
  const size_t records = metrics + 0x4C;
  const size_t gpu_relative = records + 40 * glyphs.size();
  const size_t vertices_per_glyph = 5;
  const size_t vertex_bytes = 8 * vertices_per_glyph * glyphs.size();
  const size_t index_count = 12 * glyphs.size();
  std::vector<uint8_t> data(base + gpu_relative + vertex_bytes + 2 * index_count, 0);
  std::memcpy(data.data(), "CAFF", 4);
  PutBe32(data, 0x44, uint32_t(gpu_relative));
  PutBe32(data, 0x60, uint32_t(gpu_relative));
  std::memcpy(&data[base], "vfont\0", 6);
  PutBe32(data, base + 0x34C, uint32_t(glyphs.size()));
  PutBe32(data, base + 0x35C, 0x36C);
  PutBe32(data, base + 0x360, uint32_t(hash_size));
  PutBe32(data, base + after_hash, uint32_t(metrics));
  PutBe32(data, base + after_hash + 4, uint32_t(records));
  PutBe32(data, base + metrics + 8, uint32_t(vertex_bytes));
  PutBe32(data, base + metrics + 0x10, uint32_t(index_count));
  PutBe32(data, base + metrics + 0x24, 1115);
  PutBe32(data, base + metrics + 0x28, 372);
  const size_t gpu = base + gpu_relative;
  for (size_t g = 0; g < glyphs.size(); ++g) {
    const size_t record = base + records + 40 * g;
    PutBe32(data, record, glyphs[g].first);
    float advance = glyphs[g].second;
    uint32_t advance_bits;
    std::memcpy(&advance_bits, &advance, 4);
    PutBe32(data, record + 4, advance_bits);
    PutBe32(data, record + 12, uint32_t(8 * vertices_per_glyph * g));
    PutBe32(data, record + 16, uint32_t(vertices_per_glyph));
    PutBe32(data, record + 20, uint32_t(12 * g));
    PutBe32(data, record + 24, 4);
    const float corners[5][3] = {
        {0.5f, 0.25f, 1.0f}, {0.25f, 0.0f, corner_v}, {0.75f, 0.0f, corner_v},
        {0.75f, 0.5f, corner_v}, {0.25f, 0.5f, corner_v}};
    for (size_t v = 0; v < vertices_per_glyph; ++v) {
      const size_t at = gpu + 8 * (vertices_per_glyph * g + v);
      PutBe16(data, at, Half(corners[v][0]));
      PutBe16(data, at + 2, Half(corners[v][1]));
      PutBe16(data, at + 4, 0);
      PutBe16(data, at + 6, Half(corners[v][2]));
    }
    const uint16_t fan[12] = {0, 1, 2, 0, 2, 3, 0, 3, 4, 0, 4, 1};
    for (size_t i = 0; i < 12; ++i) {
      PutBe16(data, gpu + vertex_bytes + 2 * (12 * g + i), fan[i]);
    }
  }
  return data;
}

std::vector<uint8_t> MakeXds(uint32_t width, uint32_t height, uint32_t format, uint32_t endian,
                             const char* swizzle, bool packed, std::vector<uint8_t> payload) {
  std::vector<uint8_t> data(0x34, 0);
  PutBe32(data, 0, 3);
  uint32_t selectors = 0;
  for (int channel = 0; channel < 4; ++channel) {
    selectors |= uint32_t(std::string("XYZW01").find(swizzle[channel])) << (3 * channel);
  }
  const uint32_t fetch[6] = {2u | 1u << 22 | 1u << 31, format | endian << 6,
                             (width - 1) | (height - 1) << 13, selectors << 1, 0,
                             1u << 9 | uint32_t(packed) << 11};
  for (int i = 0; i < 6; ++i) {
    PutBe32(data, 0x1C + 4 * i, fetch[i]);
  }
  data.insert(data.end(), payload.begin(), payload.end());
  return data;
}

void TestArchive() {
  const char digits[] = "123456789";
  CHECK(Crc32({reinterpret_cast<const uint8_t*>(digits), 9}) == 0xCBF43926u);

  const std::vector<uint8_t> framed = {0x00, 0x03, 1, 2, 3, 0xFF, 0x00, 0x02, 0x00, 0x02, 4, 5};
  std::vector<uint8_t> payload;
  CHECK(ParseXmemPayload(framed, 0x8002, payload));
  CHECK(payload == std::vector<uint8_t>({1, 2, 3, 4, 5}));
  CHECK(!ParseXmemPayload({framed.data(), 4}, 0x8002, payload));

  // A ZIP with one stored member.
  const std::string name = "Fonts/Test.dt";
  const std::vector<uint8_t> body = {'v', 'f', 'o', 'n', 't'};
  const uint32_t crc = Crc32(body);
  std::vector<uint8_t> zip;
  PutLe32(zip, 0x04034B50);
  for (uint16_t value : {20, 0, 0, 0, 0}) PutLe16(zip, value);
  PutLe32(zip, crc);
  PutLe32(zip, uint32_t(body.size()));
  PutLe32(zip, uint32_t(body.size()));
  PutLe16(zip, uint16_t(name.size()));
  PutLe16(zip, 0);
  zip.insert(zip.end(), name.begin(), name.end());
  zip.insert(zip.end(), body.begin(), body.end());
  const uint32_t directory_offset = uint32_t(zip.size());
  PutLe32(zip, 0x02014B50);
  for (uint16_t value : {20, 20, 0, 0, 0, 0}) PutLe16(zip, value);
  PutLe32(zip, crc);
  PutLe32(zip, uint32_t(body.size()));
  PutLe32(zip, uint32_t(body.size()));
  for (uint16_t value : {uint16_t(name.size()), uint16_t(0), uint16_t(0), uint16_t(0),
                         uint16_t(0)}) {
    PutLe16(zip, value);
  }
  PutLe32(zip, 0);
  PutLe32(zip, 0);
  zip.insert(zip.end(), name.begin(), name.end());
  const uint32_t directory_size = uint32_t(zip.size()) - directory_offset;
  PutLe32(zip, 0x06054B50);
  for (uint16_t value : {0, 0, 1, 1}) PutLe16(zip, value);
  PutLe32(zip, directory_size);
  PutLe32(zip, directory_offset);
  PutLe16(zip, 0);

  const auto path = std::filesystem::temp_directory_path() / "pinyon_shift_hostui_test.zip";
  {
    std::ofstream(path, std::ios::binary).write(reinterpret_cast<const char*>(zip.data()),
                                                std::streamsize(zip.size()));
  }
  auto archive = Fh1Archive::Open(path);
  CHECK(archive && archive->member_count() == 1);
  if (archive) {
    CHECK(archive->Contains("fonts/test.DT"));
    auto read = archive->Read("FONTS/TEST.dt");
    CHECK(read && *read == body);
    CHECK(!archive->Read("missing"));
  }
  zip[30 + name.size()] ^= 0xFF;  // corrupt the payload
  {
    std::ofstream(path, std::ios::binary).write(reinterpret_cast<const char*>(zip.data()),
                                                std::streamsize(zip.size()));
  }
  archive = Fh1Archive::Open(path);
  CHECK(archive && !archive->Read(name));
  std::filesystem::remove(path);
}

void TestVectorFont() {
  const auto data = MakeVectorFont({{'A', 0.75f}, {'?', 0.5f}});
  auto font = VectorFont::Parse(data);
  CHECK(font && font->glyph_count() == 2);
  if (!font) {
    return;
  }
  CHECK(font->ascent() > 0.74f && font->ascent() < 0.76f);
  const VectorFont::Glyph* glyph = font->Find('A');
  CHECK(glyph && glyph->advance == 0.75f && !font->Find('B'));
  // A 0.5 x 0.5 em square at 40 px/em: 20 px with a one-pixel ramp.
  const GlyphBitmap bitmap = font->Rasterize(*glyph, 40.0f);
  CHECK(bitmap.width >= 20 && bitmap.width <= 22 && bitmap.height >= 20 && bitmap.height <= 22);
  CHECK(bitmap.left >= 9 && bitmap.left <= 10 && bitmap.top >= -21 && bitmap.top <= -20);
  if (bitmap.width && bitmap.height) {
    CHECK(bitmap.alpha[size_t(bitmap.height / 2) * bitmap.width + bitmap.width / 2] == 255);
  }
  // At 41 px/em the left edge is at x = 10.25: the pixel centred at 10.5 is
  // a quarter pixel inside and gets 0.75 coverage.
  const GlyphBitmap offset = font->Rasterize(*glyph, 41.0f);
  CHECK(offset.left == 10);
  if (offset.width && offset.height) {
    const uint8_t edge = offset.alpha[size_t(offset.height / 2) * offset.width];
    CHECK(edge >= 189 && edge <= 193);
  }

  // With v = 1 everywhere the gradient is zero and the sign of f alone
  // decides: the whole square is covered, as on the title's GPU.
  auto flat = VectorFont::Parse(MakeVectorFont({{'A', 0.75f}}, 1.0f));
  if (flat) {
    const GlyphBitmap full = flat->Rasterize(*flat->Find('A'), 41.0f);
    bool all_covered = full.width > 0;
    for (int y = 1; y + 1 < full.height; ++y) {
      for (int x = 1; x + 1 < full.width; ++x) {
        all_covered &= full.alpha[size_t(y) * full.width + x] == 255;
      }
    }
    CHECK(all_covered);
  }

  auto truncated = data;
  truncated.resize(truncated.size() - 2);
  CHECK(!VectorFont::Parse(truncated));
  auto bad_index = data;
  bad_index[bad_index.size() - 1] = 9;  // beyond the glyph's five vertices
  CHECK(!VectorFont::Parse(bad_index));

  GlyphAtlas atlas(*font, 40.0f);
  CHECK(atlas.Prepare(U"AA"));
  CHECK(!atlas.Prepare(U"A"));
  const GlyphAtlas::Entry* entry = atlas.Find('A');
  CHECK(entry && entry->width == bitmap.width && entry->advance == 30.0f);
  CHECK(atlas.Find('Z') == atlas.Find('?'));
  atlas.Prepare(U"A A");
  CHECK(atlas.Measure(U"A A") == 30.0f + 10.0f + 30.0f);
  if (entry) {
    const size_t centre =
        (size_t(entry->y + entry->height / 2) * atlas.width() + entry->x + entry->width / 2) * 4;
    CHECK(atlas.rgba()[centre] == 255 && atlas.rgba()[centre + 3] == 255);
  }

  CHECK(DecodeUtf8("A\xC3\xA9\xE2\x82\xAC\xF0\x9F\x98\x80") == U"Aé€\U0001F600");
  CHECK(DecodeUtf8("\xC3") == U"�");
}

void TestTextures() {
  for (uint32_t log2 : {2u, 3u, 4u}) {
    std::set<int32_t> offsets;
    for (int32_t y = 0; y < 32; ++y) {
      for (int32_t x = 0; x < 32; ++x) {
        offsets.insert(TiledOffset2D(x, y, 32, log2));
      }
    }
    CHECK(offsets.size() == 1024 && *offsets.begin() == 0 &&
          *offsets.rbegin() == int32_t((1023u << log2)));
  }

  // RGBA8, 8-in-32 endianness, ZYXW: stored big-endian dword AABBCCDD reads
  // as X=DD Y=CC Z=BB W=AA, then R=Z, G=Y, B=X, A=W.
  std::vector<uint8_t> payload(32 * 32 * 4, 0);
  payload[0] = 0xAA;
  payload[1] = 0xBB;
  payload[2] = 0xCC;
  payload[3] = 0xDD;
  auto image = DecodeXds(MakeXds(8, 8, 50, 2, "ZYXW", false, payload));
  CHECK(image && image->width == 8 && image->rgba.size() == 8 * 8 * 4);
  if (image) {
    CHECK(image->rgba[0] == 0xBB && image->rgba[1] == 0xCC && image->rgba[2] == 0xDD &&
          image->rgba[3] == 0xAA);
  }

  // A 12x4 BC1 base in the packed mip tail, 16 texels down.
  std::vector<uint8_t> bc1(32 * 32 * 8, 0);
  const uint8_t red[8] = {0x00, 0xF8, 0x1F, 0x00, 0, 0, 0, 0};  // color0 red, all index 0
  const int32_t at = TiledOffset2D(0, 4, 32, 3);
  for (int i = 0; i < 8; ++i) {
    bc1[size_t(at) + (i ^ 1)] = red[i];
  }
  image = DecodeXds(MakeXds(12, 4, 51, 1, "XYZW", true, bc1));
  CHECK(image && image->rgba[0] == 255 && image->rgba[1] == 0 && image->rgba[3] == 255);

  // DXT3A reads the same value in every component.
  std::vector<uint8_t> dxt3a(32 * 32 * 8, 0);
  const uint8_t nibbles[8] = {0x21, 0x43, 0x65, 0x87, 0xA9, 0xCB, 0xED, 0x0F};
  for (int i = 0; i < 8; ++i) {
    dxt3a[size_t(i ^ 1)] = nibbles[i];
  }
  image = DecodeXds(MakeXds(4, 4, 58, 1, "111W", false, dxt3a));
  CHECK(image && image->rgba[0] == 255 && image->rgba[3] == 17 && image->rgba[63] == 0);

  CHECK(!DecodeXds(MakeXds(8, 8, 50, 2, "XYZW", false, std::vector<uint8_t>(16))));
  CHECK(!DecodeXds(MakeXds(8, 8, 33, 2, "XYZW", false, payload)));
}

void TestMenu() {
  int volume = 5;
  int activations = 0;
  std::vector<MenuRow> rows(4);
  rows[0].label = "RESUME";
  rows[0].activate = [&] { ++activations; };
  rows[1].label = "DISABLED";
  rows[1].enabled = [] { return false; };
  rows[2].label = "VOLUME";
  rows[2].value = [&] { return std::to_string(volume); };
  rows[2].adjust = [&](int direction) { volume += direction; };
  rows[3].label = "QUIT";
  MenuScreen screen("SETTINGS", std::move(rows));
  CHECK(screen.focus() == 0);
  CHECK(screen.Handle(NavCommand::kAccept) == MenuScreen::Result::kChanged && activations == 1);
  CHECK(screen.Handle(NavCommand::kDown) == MenuScreen::Result::kChanged && screen.focus() == 2);
  CHECK(screen.Handle(NavCommand::kRight) == MenuScreen::Result::kChanged && volume == 6);
  CHECK(screen.Handle(NavCommand::kLeft) == MenuScreen::Result::kChanged && volume == 5);
  CHECK(screen.Handle(NavCommand::kAccept) == MenuScreen::Result::kChanged && volume == 6);
  CHECK(screen.Handle(NavCommand::kDown) == MenuScreen::Result::kChanged && screen.focus() == 3);
  CHECK(screen.Handle(NavCommand::kAccept) == MenuScreen::Result::kNone);
  CHECK(screen.Handle(NavCommand::kDown) == MenuScreen::Result::kChanged && screen.focus() == 0);
  CHECK(screen.Handle(NavCommand::kUp) == MenuScreen::Result::kChanged && screen.focus() == 3);
  CHECK(!screen.SetFocus(1) && screen.SetFocus(2) && screen.focus() == 2);
  CHECK(screen.Handle(NavCommand::kBack) == MenuScreen::Result::kBack);
  CHECK(screen.Handle(NavCommand::kClose) == MenuScreen::Result::kBack);

  // A keybind prompt takes the next press before navigation does.
  MenuScreen prompt("PRESS A KEY", {});
  CHECK(!prompt.captures_keys());
  int captured = 0;
  prompt.set_key_capture([&](int virtual_key) { captured = virtual_key; });
  CHECK(prompt.captures_keys());
  prompt.CaptureKey(0x41);
  CHECK(captured == 0x41);
  CHECK(prompt.Handle(NavCommand::kAccept) == MenuScreen::Result::kNone);
  CHECK(prompt.Handle(NavCommand::kBack) == MenuScreen::Result::kBack);

  PadNavigator pad;
  using Commands = std::vector<NavCommand>;
  // The press that opened the menu is ignored until released.
  CHECK(pad.Poll(PadNavigator::kButtonA | PadNavigator::kDpadDown, 0, 0, 0).empty());
  CHECK(pad.Poll(PadNavigator::kButtonA | PadNavigator::kDpadDown, 0, 0, 1000).empty());
  CHECK(pad.Poll(0, 0, 0, 1010).empty());
  CHECK(pad.Poll(PadNavigator::kDpadDown, 0, 0, 1020) == Commands{NavCommand::kDown});
  CHECK(pad.Poll(PadNavigator::kDpadDown, 0, 0, 1300).empty());
  CHECK(pad.Poll(PadNavigator::kDpadDown, 0, 0, 1420) == Commands{NavCommand::kDown});
  CHECK(pad.Poll(PadNavigator::kDpadDown, 0, 0, 1500).empty());
  CHECK(pad.Poll(PadNavigator::kDpadDown, 0, 0, 1530) == Commands{NavCommand::kDown});
  CHECK(pad.Poll(0, 0, 20000, 1600) == Commands{NavCommand::kUp});
  CHECK(pad.Poll(0, -20000, 0, 1610) == Commands{NavCommand::kLeft});
  CHECK(pad.Poll(PadNavigator::kButtonA, 0, 0, 1620) == Commands{NavCommand::kAccept});
  CHECK(pad.Poll(PadNavigator::kButtonA, 0, 0, 1630).empty());
  CHECK(pad.Poll(PadNavigator::kButtonB, 0, 0, 1640) == Commands{NavCommand::kBack});
  CHECK(pad.Poll(PadNavigator::kStart, 0, 0, 1650) == Commands{NavCommand::kClose});
  pad.Reset();
  CHECK(pad.Poll(PadNavigator::kButtonB, 0, 0, 1660).empty());
}

}  // namespace

// Developer aid: rasterize `text` from a font in the title's Fonts.zip into an
// atlas and write it as a PGM, to compare with the game.
int DumpAtlas(const char* fonts_zip, const char* member, float pixels_per_em, const char* text,
              const char* output) {
  auto archive = Fh1Archive::Open(fonts_zip);
  auto data = archive ? archive->Read(member) : std::nullopt;
  auto font = data ? VectorFont::Parse(*data) : std::nullopt;
  if (!font) {
    std::fprintf(stderr, "cannot load %s from %s\n", member, fonts_zip);
    return 1;
  }
  GlyphAtlas atlas(*font, pixels_per_em);
  atlas.Prepare(DecodeUtf8(text));
  std::ofstream out(output, std::ios::binary);
  out << "P5\n" << atlas.width() << " " << atlas.height() << "\n255\n";
  for (size_t i = 3; i < atlas.rgba().size(); i += 4) {
    out.put(char(atlas.rgba()[i]));
  }
  std::printf("%u x %u, %zu glyphs in font\n", atlas.width(), atlas.height(), font->glyph_count());
  return 0;
}

int main(int argc, char** argv) {
  if (argc == 7 && std::string(argv[1]) == "--dump-atlas") {
    return DumpAtlas(argv[2], argv[3], std::stof(argv[4]), argv[5], argv[6]);
  }
  TestArchive();
  TestVectorFont();
  TestTextures();
  TestMenu();
  if (failures) {
    std::fprintf(stderr, "%d check(s) failed\n", failures);
    return 1;
  }
  std::puts("hostui tests passed");
  return 0;
}
